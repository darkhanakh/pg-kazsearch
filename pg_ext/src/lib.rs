use pgrx::prelude::*;
use std::ffi::CStr;
use std::os::raw::c_char;

use kazsearch_core::lexicon::Lexicon;
use kazsearch_core::{PenaltyWeights, ScriptMode, StemConfig};

pgrx::pg_module_magic!();

fn is_weight_param(name: &str) -> bool {
    matches!(
        name,
        "w_no_strip" | "w_short_char" | "w_no_syll" | "w_two_char" | "w_three_one"
            | "w_deriv" | "w_weak" | "w_single_char" | "w_verb_all_weak" | "w_nik_deriv"
            | "w_final_cons" | "w_nominal_inf" | "w_verbal_inf" | "w_removed" | "w_verb_track"
    )
}

fn try_parse_weight(name: &str, value: &str, w: &mut PenaltyWeights) -> Option<()> {
    let v: f64 = value.parse().ok()?;
    match name {
        "w_no_strip" => w.w_no_strip = v,
        "w_short_char" => w.w_short_char = v,
        "w_no_syll" => w.w_no_syll = v,
        "w_two_char" => w.w_two_char = v,
        "w_three_one" => w.w_three_one = v,
        "w_deriv" => w.w_deriv = v,
        "w_weak" => w.w_weak = v,
        "w_single_char" => w.w_single_char = v,
        "w_verb_all_weak" => w.w_verb_all_weak = v,
        "w_nik_deriv" => w.w_nik_deriv = v,
        "w_final_cons" => w.w_final_cons = v,
        "w_nominal_inf" => w.w_nominal_inf = v,
        "w_verbal_inf" => w.w_verbal_inf = v,
        "w_removed" => w.w_removed = v,
        "w_verb_track" => w.w_verb_track = v,
        _ => return None,
    }
    Some(())
}

unsafe fn load_lexicon_from_pg(lexicon_name: &str) -> Lexicon {
    let c_name = std::ffi::CString::new(lexicon_name).expect("invalid lexicon name");
    let c_ext = std::ffi::CString::new("dict").expect("invalid extension");
    let path_ptr = pg_sys::get_tsearch_config_filename(c_name.as_ptr(), c_ext.as_ptr());
    if path_ptr.is_null() {
        pgrx::error!("could not find lexicon file for \"{}\"", lexicon_name);
    }
    let path_str = CStr::from_ptr(path_ptr).to_str().unwrap_or("");

    // Lexicon::load also picks up the optional kaz_stems.dict.verbs sibling,
    // which gates the verb-root reductions (-у/-ю, -ған, converb -п).
    let lexicon = match Lexicon::load(path_str) {
        Ok(lex) => lex,
        Err(e) => {
            pgrx::error!("could not load lexicon file \"{}\": {}", path_str, e);
        }
    };
    pg_sys::pfree(path_ptr as *mut _);
    lexicon
}

#[pg_extern(sql = "
CREATE OR REPLACE FUNCTION pg_kazsearch_init(internal)
RETURNS internal
AS 'MODULE_PATHNAME', 'pg_kazsearch_init_wrapper'
LANGUAGE C STRICT;
")]
fn pg_kazsearch_init(dict_options: pgrx::Internal) -> pgrx::Internal {
    let mut cfg = StemConfig::default();
    let mut lexicon_name: Option<String> = None;

    unsafe {
        if let Some(datum) = dict_options.unwrap() {
            let list_ptr = datum.cast_mut_ptr::<pg_sys::List>();
            if !list_ptr.is_null() {
                let len = (*list_ptr).length as usize;
                let elements = (*list_ptr).elements;
                for i in 0..len {
                    let cell = *elements.add(i);
                    let defel = cell.ptr_value as *mut pg_sys::DefElem;
                    let name = CStr::from_ptr((*defel).defname)
                        .to_str()
                        .unwrap_or("");

                    if name == "derivation" {
                        cfg.derivation = pg_sys::defGetBoolean(defel);
                    } else if name == "max_steps" {
                        let val = pg_sys::defGetString(defel);
                        let val_str = CStr::from_ptr(val).to_str().unwrap_or("");
                        cfg.max_steps = match val_str.parse::<i32>() {
                            Ok(v) => v,
                            Err(_) => pgrx::error!(
                                "invalid max_steps for pg_kazsearch: \"{}\" (expected integer)",
                                val_str
                            ),
                        };
                    } else if name == "lexicon" {
                        let val = pg_sys::defGetString(defel);
                        lexicon_name =
                            Some(CStr::from_ptr(val).to_str().unwrap_or("").to_string());
                    } else if name == "script_mode" {
                        let val = pg_sys::defGetString(defel);
                        let val_str = CStr::from_ptr(val).to_str().unwrap_or("auto");
                        cfg.script_mode = match val_str {
                            "auto" => ScriptMode::Auto,
                            "cyrillic_only" => ScriptMode::CyrillicOnly,
                            _ => {
                                pgrx::error!(
                                    "invalid script_mode for pg_kazsearch: \"{}\" (expected auto or cyrillic_only)",
                                    val_str
                                );
                            }
                        };
                    } else {
                        let val = pg_sys::defGetString(defel);
                        let val_str = CStr::from_ptr(val).to_str().unwrap_or("");
                        if !is_weight_param(name) {
                            pgrx::error!(
                                "unrecognized pg_kazsearch parameter: \"{}\"",
                                name
                            );
                        }
                        if try_parse_weight(name, val_str, &mut cfg.weights).is_none() {
                            pgrx::error!(
                                "invalid value for pg_kazsearch parameter \"{}\": \"{}\" (expected number)",
                                name,
                                val_str
                            );
                        }
                    }
                }
            }
        }
    }

    if cfg.max_steps < 1 {
        cfg.max_steps = 1;
    }
    if cfg.max_steps > 16 {
        cfg.max_steps = 16;
    }
    if let Some(ref lex_name) = lexicon_name {
        if !lex_name.is_empty() {
            cfg.lexicon = Some(unsafe { load_lexicon_from_pg(lex_name) });
        }
    }

    pgrx::Internal::new(cfg)
}

#[pg_extern(sql = "
CREATE OR REPLACE FUNCTION pg_kazsearch_lexize(internal, internal, internal, internal)
RETURNS internal
AS 'MODULE_PATHNAME', 'pg_kazsearch_lexize_wrapper'
LANGUAGE C STRICT;
")]
fn pg_kazsearch_lexize(
    dict_state: pgrx::Internal,
    input: pgrx::Internal,
    len: pgrx::Internal,
    _dst: pgrx::Internal,
) -> pgrx::Internal {
    unsafe {
        let cfg: &StemConfig = match dict_state.get::<StemConfig>() {
            Some(c) => c,
            None => return pgrx::Internal::default(),
        };

        let input_datum = match input.unwrap() {
            Some(d) => d,
            None => return pgrx::Internal::default(),
        };
        let input_ptr = input_datum.cast_mut_ptr::<c_char>();

        let len_datum = match len.unwrap() {
            Some(d) => d,
            None => return pgrx::Internal::default(),
        };
        let byte_len = len_datum.value() as i32;

        if input_ptr.is_null() || byte_len <= 0 {
            return pgrx::Internal::default();
        }

        let input_bytes =
            std::slice::from_raw_parts(input_ptr as *const u8, byte_len as usize);
        let input_str = match std::str::from_utf8(input_bytes) {
            Ok(s) => s,
            Err(_) => return pgrx::Internal::default(),
        };

        let result = kazsearch_core::stem(input_str, cfg);

        let res = pg_sys::palloc0(std::mem::size_of::<pg_sys::TSLexeme>() * 2)
            as *mut pg_sys::TSLexeme;

        let lexeme_cstr = std::ffi::CString::new(result.as_str()).unwrap_or_default();
        let lexeme_bytes = lexeme_cstr.as_bytes_with_nul();
        let lexeme_pg = pg_sys::palloc(lexeme_bytes.len()) as *mut c_char;
        std::ptr::copy_nonoverlapping(
            lexeme_bytes.as_ptr(),
            lexeme_pg as *mut u8,
            lexeme_bytes.len(),
        );

        (*res).lexeme = lexeme_pg;
        (*res).nvariant = 0;
        (*res.add(1)).lexeme = std::ptr::null_mut();

        pgrx::Internal::from(Some(pg_sys::Datum::from(res)))
    }
}

extension_sql!(
    r#"
CREATE TEXT SEARCH TEMPLATE pg_kazsearch_template (
    INIT = pg_kazsearch_init,
    LEXIZE = pg_kazsearch_lexize
);

CREATE TEXT SEARCH DICTIONARY pg_kazsearch_stop (
    TEMPLATE = pg_catalog.simple,
    STOPWORDS = kaz_stopwords,
    ACCEPT = false
);

CREATE TEXT SEARCH DICTIONARY pg_kazsearch_dict (
    TEMPLATE = pg_kazsearch_template,
    derivation = true,
    max_steps = 8,
    lexicon = kaz_stems,
    script_mode = auto
);

CREATE TEXT SEARCH CONFIGURATION kazakh_cfg (PARSER = pg_catalog.default);

ALTER TEXT SEARCH CONFIGURATION kazakh_cfg
    ALTER MAPPING FOR asciiword, asciihword, hword_asciipart,
                      word, hword, hword_part
    WITH pg_kazsearch_stop, pg_kazsearch_dict, simple;

-- Numbers, URLs, emails, etc. are not Kazakh words but must still be
-- searchable (dates, percentages, versions in news text). Without these
-- mappings such tokens are dropped from the tsvector entirely.
ALTER TEXT SEARCH CONFIGURATION kazakh_cfg
    ADD MAPPING FOR numword, numhword, hword_numpart,
                    int, uint, float, sfloat, version,
                    email, url, url_path, host, file
    WITH simple;
"#,
    name = "kazakh_cfg_setup",
    requires = [pg_kazsearch_init, pg_kazsearch_lexize]
);
