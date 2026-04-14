use std::ffi::c_char;
use std::path::Path;
use std::sync::{Mutex, OnceLock};

use jni::objects::{JClass, JString};
use jni::sys::{jint, jstring};
use jni::EnvUnowned;
use kazsearch_core::lexicon::Lexicon;
pub use kazsearch_core::stem;
pub use kazsearch_core::StemConfig;

const KAZSEARCH_OK: i32 = 0;
const KAZSEARCH_ERR_NULL_PTR: i32 = -1;
const KAZSEARCH_ERR_UTF8: i32 = -2;
const KAZSEARCH_ERR_LEXICON: i32 = -3;
const KAZSEARCH_ERR_BUFFER_TOO_SMALL: i32 = -4;

fn config_store() -> &'static Mutex<StemConfig> {
    static CONFIG: OnceLock<Mutex<StemConfig>> = OnceLock::new();
    CONFIG.get_or_init(|| Mutex::new(StemConfig::default()))
}

fn load_lexicon(path: &str) -> Result<Option<Lexicon>, ()> {
    let trimmed = path.trim();
    if trimmed.is_empty() {
        return Ok(None);
    }

    Lexicon::load(Path::new(trimmed)).map(Some).map_err(|_| ())
}

fn set_config(lexicon_path: Option<&str>) -> i32 {
    let mut cfg = StemConfig::default();

    if let Some(path) = lexicon_path {
        cfg.lexicon = match load_lexicon(path) {
            Ok(v) => v,
            Err(_) => return KAZSEARCH_ERR_LEXICON,
        };
    }

    match config_store().lock() {
        Ok(mut store) => {
            *store = cfg;
            KAZSEARCH_OK
        }
        Err(_) => KAZSEARCH_ERR_LEXICON,
    }
}

fn stem_with_current_config(input: &str) -> Result<String, i32> {
    let cfg = match config_store().lock() {
        Ok(guard) => guard.clone(),
        Err(_) => return Err(KAZSEARCH_ERR_LEXICON),
    };
    Ok(stem(input, &cfg))
}

#[no_mangle]
pub unsafe extern "C" fn kazsearch_init(lexicon_path: *const c_char) -> i32 {
    if lexicon_path.is_null() {
        return set_config(None);
    }

    let cstr = unsafe { std::ffi::CStr::from_ptr(lexicon_path) };
    let path = match cstr.to_str() {
        Ok(v) => v,
        Err(_) => return KAZSEARCH_ERR_UTF8,
    };

    set_config(Some(path))
}

#[no_mangle]
pub unsafe extern "C" fn kazsearch_stem(
    input_ptr: *const c_char,
    input_len: usize,
    out_ptr: *mut c_char,
    out_len: usize,
) -> i32 {
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
}

#[no_mangle]
pub extern "system" fn Java_io_github_darkhanakh_kazsearch_KazakhStemmerNative_init0(
    mut unowned_env: EnvUnowned<'_>,
    _class: JClass<'_>,
    lexicon_path: JString<'_>,
) -> jint {
    if lexicon_path.is_null() {
        return set_config(None);
    }

    let outcome = unowned_env.with_env(|env| -> jni::errors::Result<jint> {
        let path = lexicon_path.try_to_string(env)?;
        Ok(set_config(Some(path.as_str())))
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
