use std::ffi::c_char;
use std::path::Path;
use std::sync::{Arc, OnceLock, RwLock};

use jni::objects::{JClass, JString};
use jni::sys::{jint, jstring};
use jni::EnvUnowned;
use kazsearch_core::lexicon::Lexicon;
pub use kazsearch_core::stem;
pub use kazsearch_core::KeyboardMode;
pub use kazsearch_core::ScriptMode;
pub use kazsearch_core::StemConfig;

const KAZSEARCH_OK: i32 = 0;
const KAZSEARCH_ERR_NULL_PTR: i32 = -1;
const KAZSEARCH_ERR_UTF8: i32 = -2;
const KAZSEARCH_ERR_LEXICON: i32 = -3;
const KAZSEARCH_ERR_BUFFER_TOO_SMALL: i32 = -4;
const KAZSEARCH_ERR_CONFIG: i32 = -6;

/// Config is stored behind an `Arc` so the per-token hot path only clones a
/// pointer, never the `StemConfig` itself (which owns the entire lexicon
/// `HashSet` — cloning it per token is catastrophic under concurrent
/// Elasticsearch analysis threads).
fn config_store() -> &'static RwLock<Arc<StemConfig>> {
    static CONFIG: OnceLock<RwLock<Arc<StemConfig>>> = OnceLock::new();
    CONFIG.get_or_init(|| RwLock::new(Arc::new(StemConfig::default())))
}

fn load_lexicon(path: &str) -> Result<Option<Lexicon>, ()> {
    let trimmed = path.trim();
    if trimmed.is_empty() {
        return Ok(None);
    }

    Lexicon::load(Path::new(trimmed)).map(Some).map_err(|_| ())
}

fn parse_script_mode(raw: &str) -> Result<ScriptMode, ()> {
    match raw.trim().to_ascii_lowercase().as_str() {
        "" | "auto" => Ok(ScriptMode::Auto),
        "cyrillic_only" | "cyrillic-only" | "cyrillic" => Ok(ScriptMode::CyrillicOnly),
        _ => Err(()),
    }
}

fn parse_keyboard_mode(raw: &str) -> Result<KeyboardMode, ()> {
    match raw.trim().to_ascii_lowercase().as_str() {
        "" | "exact" => Ok(KeyboardMode::Exact),
        "restore" => Ok(KeyboardMode::Restore),
        _ => Err(()),
    }
}

fn set_config(lexicon_path: Option<&str>, script_mode: ScriptMode, keyboard: KeyboardMode) -> i32 {
    let mut cfg = StemConfig::default();
    cfg.script_mode = script_mode;
    cfg.keyboard = keyboard;

    if let Some(path) = lexicon_path {
        cfg.lexicon = match load_lexicon(path) {
            Ok(v) => v,
            Err(_) => return KAZSEARCH_ERR_LEXICON,
        };
    }

    let mut store = config_store()
        .write()
        .unwrap_or_else(|poisoned| poisoned.into_inner());
    *store = Arc::new(cfg);
    KAZSEARCH_OK
}

fn stem_with_current_config(input: &str) -> Result<String, i32> {
    let cfg = Arc::clone(
        &config_store()
            .read()
            .unwrap_or_else(|poisoned| poisoned.into_inner()),
    );
    Ok(stem(input, &cfg))
}

const KAZSEARCH_ERR_PANIC: i32 = -5;

#[no_mangle]
pub unsafe extern "C" fn kazsearch_init(lexicon_path: *const c_char) -> i32 {
    // Unwinding across an `extern "C"` boundary is undefined behavior;
    // contain any panic and surface it as an error code.
    std::panic::catch_unwind(|| {
        if lexicon_path.is_null() {
            return set_config(None, ScriptMode::Auto, KeyboardMode::Exact);
        }

        let cstr = unsafe { std::ffi::CStr::from_ptr(lexicon_path) };
        let path = match cstr.to_str() {
            Ok(v) => v,
            Err(_) => return KAZSEARCH_ERR_UTF8,
        };

        set_config(Some(path), ScriptMode::Auto, KeyboardMode::Exact)
    })
    .unwrap_or(KAZSEARCH_ERR_PANIC)
}

#[no_mangle]
pub unsafe extern "C" fn kazsearch_stem(
    input_ptr: *const c_char,
    input_len: usize,
    out_ptr: *mut c_char,
    out_len: usize,
) -> i32 {
    std::panic::catch_unwind(|| {
        if input_ptr.is_null() || out_ptr.is_null() {
            return KAZSEARCH_ERR_NULL_PTR;
        }

        let input_bytes = unsafe { std::slice::from_raw_parts(input_ptr.cast::<u8>(), input_len) };
        let input = match std::str::from_utf8(input_bytes) {
            Ok(v) => v,
            Err(_) => return KAZSEARCH_ERR_UTF8,
        };

        let stemmed = match stem_with_current_config(input) {
            Ok(v) => v,
            Err(code) => return code,
        };
        let stemmed_bytes = stemmed.as_bytes();
        let required = stemmed_bytes.len() + 1;
        if out_len < required {
            return KAZSEARCH_ERR_BUFFER_TOO_SMALL;
        }

        unsafe {
            std::ptr::copy_nonoverlapping(stemmed_bytes.as_ptr(), out_ptr.cast::<u8>(), stemmed_bytes.len());
            *out_ptr.add(stemmed_bytes.len()) = 0;
        }

        stemmed_bytes.len() as i32
    })
    .unwrap_or(KAZSEARCH_ERR_PANIC)
}

#[no_mangle]
pub extern "system" fn Java_io_github_darkhanakh_kazsearch_KazakhStemmerNative_init0(
    mut unowned_env: EnvUnowned<'_>,
    _class: JClass<'_>,
    lexicon_path: JString<'_>,
    script_mode: JString<'_>,
    keyboard: JString<'_>,
) -> jint {
    let outcome = unowned_env.with_env(|env| -> jni::errors::Result<jint> {
        let mode = if script_mode.is_null() {
            ScriptMode::Auto
        } else {
            let raw = script_mode.try_to_string(env)?;
            match parse_script_mode(raw.as_str()) {
                Ok(v) => v,
                Err(_) => return Ok(KAZSEARCH_ERR_CONFIG),
            }
        };
        let keyboard = if keyboard.is_null() {
            KeyboardMode::Exact
        } else {
            let raw = keyboard.try_to_string(env)?;
            match parse_keyboard_mode(raw.as_str()) {
                Ok(v) => v,
                Err(_) => return Ok(KAZSEARCH_ERR_CONFIG),
            }
        };

        if lexicon_path.is_null() {
            return Ok(set_config(None, mode, keyboard));
        }
        let path = lexicon_path.try_to_string(env)?;
        Ok(set_config(Some(path.as_str()), mode, keyboard))
    });
    outcome.resolve::<jni::errors::ThrowRuntimeExAndDefault>()
}

#[no_mangle]
pub extern "system" fn Java_io_github_darkhanakh_kazsearch_KazakhStemmerNative_stem0(
    mut unowned_env: EnvUnowned<'_>,
    _class: JClass<'_>,
    input: JString<'_>,
) -> jstring {
    if input.is_null() {
        return std::ptr::null_mut();
    }

    let outcome = unowned_env.with_env(|env| -> jni::errors::Result<jstring> {
        let input_rs = input.try_to_string(env)?;
        let stemmed = match stem_with_current_config(input_rs.as_str()) {
            Ok(v) => v,
            Err(_) => return Ok(std::ptr::null_mut()),
        };
        let output = JString::from_str(env, stemmed)?;
        Ok(output.into_raw())
    });
    outcome.resolve::<jni::errors::ThrowRuntimeExAndDefault>()
}
