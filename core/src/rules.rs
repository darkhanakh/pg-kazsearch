pub const HARM_ANY: u8 = 0;
pub const HARM_BACK: u8 = 1;
pub const HARM_FRONT: u8 = 2;

pub const LAYER_PRED: i32 = 1;
pub const LAYER_CASE: i32 = 2;
pub const LAYER_POSS: i32 = 3;
pub const LAYER_PLUR: i32 = 4;
pub const LAYER_DERIV: i32 = 5;
pub const LAYER_VPERSON: i32 = 11;
pub const LAYER_VTENSE: i32 = 12;
pub const LAYER_VNEG: i32 = 13;
pub const LAYER_VVOICE: i32 = 14;

#[derive(Clone, Debug)]
pub struct SuffixRule {
    pub suffix: &'static str,
    pub harmony: u8,
    pub weak: bool,
}

#[derive(Clone, Debug)]
pub struct LayerDef {
    pub rules: &'static [SuffixRule],
    pub layer_id: i32,
    pub repeat: bool,
    pub kind: i32, // 1=nominal_inf, 2=verbal_inf, 3=deriv
}

macro_rules! sfx {
    ($s:expr, $h:expr, 0) => { SuffixRule { suffix: $s, harmony: $h, weak: false } };
    ($s:expr, $h:expr, 1) => { SuffixRule { suffix: $s, harmony: $h, weak: true } };
}

static PRED_RULES: &[SuffixRule] = &[
    sfx!("сыңдар", HARM_ANY, 0), sfx!("сіңдер", HARM_ANY, 0), sfx!("сыздар", HARM_ANY, 0), sfx!("сіздер", HARM_ANY, 0),
    sfx!("сыз", HARM_BACK, 0), sfx!("сіз", HARM_FRONT, 0), sfx!("сың", HARM_BACK, 0), sfx!("сің", HARM_FRONT, 0),
    sfx!("мын", HARM_BACK, 0), sfx!("мін", HARM_FRONT, 0), sfx!("бын", HARM_BACK, 0), sfx!("бін", HARM_FRONT, 0),
    sfx!("пын", HARM_BACK, 0), sfx!("пін", HARM_FRONT, 0), sfx!("мыз", HARM_BACK, 0), sfx!("міз", HARM_FRONT, 0),
];

static CASE_RULES: &[SuffixRule] = &[
    sfx!("ның", HARM_BACK, 0), sfx!("нің", HARM_FRONT, 0), sfx!("дың", HARM_BACK, 0),
    sfx!("дің", HARM_FRONT, 0), sfx!("тың", HARM_BACK, 0), sfx!("тің", HARM_FRONT, 0), sfx!("нан", HARM_BACK, 0),
    sfx!("нен", HARM_FRONT, 0), sfx!("дан", HARM_BACK, 0), sfx!("ден", HARM_FRONT, 0), sfx!("тан", HARM_BACK, 0),
    sfx!("тен", HARM_FRONT, 0), sfx!("нда", HARM_BACK, 0), sfx!("нде", HARM_FRONT, 0), sfx!("бен", HARM_ANY, 0),
    sfx!("пен", HARM_ANY, 0), sfx!("мен", HARM_ANY, 0), sfx!("ға", HARM_BACK, 0), sfx!("ге", HARM_FRONT, 0),
    sfx!("қа", HARM_BACK, 0), sfx!("ке", HARM_FRONT, 0), sfx!("на", HARM_BACK, 0), sfx!("не", HARM_FRONT, 0),
    sfx!("ңа", HARM_BACK, 0), sfx!("ңе", HARM_FRONT, 0), sfx!("ны", HARM_BACK, 0), sfx!("ні", HARM_FRONT, 0),
    sfx!("а", HARM_BACK, 1), sfx!("е", HARM_FRONT, 1), sfx!("ды", HARM_BACK, 0), sfx!("ді", HARM_FRONT, 0), sfx!("ты", HARM_BACK, 0), sfx!("ті", HARM_FRONT, 0),
    sfx!("ын", HARM_BACK, 0), sfx!("ін", HARM_FRONT, 0), sfx!("да", HARM_BACK, 0), sfx!("де", HARM_FRONT, 0),
    sfx!("та", HARM_BACK, 0), sfx!("те", HARM_FRONT, 0), sfx!("н", HARM_ANY, 1),
];

static POSS_RULES: &[SuffixRule] = &[
    sfx!("ымыз", HARM_BACK, 0), sfx!("іміз", HARM_FRONT, 0), sfx!("ыңыз", HARM_BACK, 0), sfx!("іңіз", HARM_FRONT, 0),
    sfx!("лары", HARM_BACK, 0), sfx!("лері", HARM_FRONT, 0), sfx!("дары", HARM_BACK, 0), sfx!("дері", HARM_FRONT, 0),
    sfx!("тары", HARM_BACK, 0), sfx!("тері", HARM_FRONT, 0), sfx!("мыз", HARM_BACK, 0), sfx!("міз", HARM_FRONT, 0),
    sfx!("ңыз", HARM_BACK, 0), sfx!("ңіз", HARM_FRONT, 0), sfx!("сы", HARM_BACK, 1), sfx!("сі", HARM_FRONT, 1),
    sfx!("ым", HARM_BACK, 0), sfx!("ім", HARM_FRONT, 0), sfx!("ың", HARM_BACK, 0), sfx!("ің", HARM_FRONT, 0),
    sfx!("ы", HARM_BACK, 1), sfx!("і", HARM_FRONT, 1), sfx!("м", HARM_ANY, 1), sfx!("ң", HARM_ANY, 1),
];

static PLUR_RULES: &[SuffixRule] = &[
    sfx!("дар", HARM_BACK, 0), sfx!("дер", HARM_FRONT, 0), sfx!("лар", HARM_BACK, 0),
    sfx!("лер", HARM_FRONT, 0), sfx!("тар", HARM_BACK, 0), sfx!("тер", HARM_FRONT, 0),
];

static DERIV_RULES: &[SuffixRule] = &[
    sfx!("ндағы", HARM_BACK, 0), sfx!("ндегі", HARM_FRONT, 0), sfx!("дағы", HARM_BACK, 0), sfx!("дегі", HARM_FRONT, 0),
    sfx!("тағы", HARM_BACK, 0), sfx!("тегі", HARM_FRONT, 0), sfx!("нікі", HARM_ANY, 1), sfx!("дікі", HARM_ANY, 1),
    sfx!("тікі", HARM_ANY, 1),
    sfx!("ырақ", HARM_BACK, 0), sfx!("ірек", HARM_FRONT, 0), sfx!("рақ", HARM_BACK, 0), sfx!("рек", HARM_FRONT, 0),
    sfx!("лау", HARM_BACK, 0), sfx!("леу", HARM_FRONT, 0), sfx!("дау", HARM_BACK, 0), sfx!("деу", HARM_FRONT, 0),
    sfx!("тау", HARM_BACK, 0), sfx!("теу", HARM_FRONT, 0), sfx!("лық", HARM_BACK, 0), sfx!("лік", HARM_FRONT, 0),
    sfx!("дық", HARM_BACK, 0), sfx!("дік", HARM_FRONT, 0), sfx!("тық", HARM_BACK, 0), sfx!("тік", HARM_FRONT, 0),
    sfx!("шы", HARM_BACK, 1), sfx!("ші", HARM_FRONT, 1), sfx!("ша", HARM_BACK, 1), sfx!("ше", HARM_FRONT, 1),
    sfx!("сыз", HARM_BACK, 0), sfx!("сіз", HARM_FRONT, 0), sfx!("ғы", HARM_BACK, 1), sfx!("гі", HARM_FRONT, 1),
    sfx!("ншы", HARM_BACK, 0), sfx!("нші", HARM_FRONT, 0), sfx!("дай", HARM_BACK, 0), sfx!("дей", HARM_FRONT, 0),
    sfx!("тай", HARM_BACK, 0), sfx!("тей", HARM_FRONT, 0), sfx!("ба", HARM_BACK, 1), sfx!("бе", HARM_FRONT, 1),
];

static VPERSON_RULES: &[SuffixRule] = &[
    sfx!("сыңдар", HARM_ANY, 0), sfx!("сіңдер", HARM_ANY, 0), sfx!("сыздар", HARM_BACK, 0), sfx!("сіздер", HARM_FRONT, 0),
    sfx!("мыз", HARM_BACK, 0), sfx!("міз", HARM_FRONT, 0), sfx!("сыз", HARM_BACK, 0), sfx!("сіз", HARM_FRONT, 0),
    sfx!("сың", HARM_BACK, 0), sfx!("сің", HARM_FRONT, 0), sfx!("мын", HARM_BACK, 0), sfx!("мін", HARM_FRONT, 0),
    sfx!("бын", HARM_BACK, 0), sfx!("бін", HARM_FRONT, 0), sfx!("пын", HARM_BACK, 0), sfx!("пін", HARM_FRONT, 0),
    sfx!("м", HARM_ANY, 1), sfx!("ң", HARM_ANY, 1), sfx!("қ", HARM_BACK, 1), sfx!("к", HARM_FRONT, 1),
];

static VTENSE_RULES: &[SuffixRule] = &[
    sfx!("майды", HARM_BACK, 0), sfx!("мейді", HARM_FRONT, 0), sfx!("байды", HARM_BACK, 0), sfx!("бейді", HARM_FRONT, 0),
    sfx!("пайды", HARM_BACK, 0), sfx!("пейді", HARM_FRONT, 0), sfx!("атын", HARM_BACK, 0), sfx!("етін", HARM_FRONT, 0),
    sfx!("йтын", HARM_BACK, 0), sfx!("йтін", HARM_FRONT, 0), sfx!("ыпты", HARM_BACK, 0), sfx!("іпті", HARM_FRONT, 0),
    sfx!("пты", HARM_BACK, 0), sfx!("пті", HARM_FRONT, 0), sfx!("йды", HARM_ANY, 0), sfx!("йді", HARM_ANY, 0),
    sfx!("ады", HARM_BACK, 0), sfx!("еді", HARM_FRONT, 0), sfx!("ған", HARM_BACK, 0), sfx!("ген", HARM_FRONT, 0),
    sfx!("қан", HARM_BACK, 0), sfx!("кен", HARM_FRONT, 0), sfx!("май", HARM_BACK, 0), sfx!("мей", HARM_FRONT, 0),
    sfx!("саң", HARM_BACK, 0), sfx!("сең", HARM_FRONT, 0), sfx!("сақ", HARM_BACK, 0), sfx!("сек", HARM_FRONT, 0),
    sfx!("тын", HARM_BACK, 0), sfx!("тін", HARM_FRONT, 0), sfx!("мақ", HARM_BACK, 0), sfx!("мек", HARM_FRONT, 0),
    sfx!("бақ", HARM_BACK, 0), sfx!("бек", HARM_FRONT, 0), sfx!("пақ", HARM_BACK, 0), sfx!("пек", HARM_FRONT, 0),
    sfx!("ды", HARM_BACK, 0), sfx!("ді", HARM_FRONT, 0), sfx!("ты", HARM_BACK, 0), sfx!("ті", HARM_FRONT, 0),
    sfx!("ып", HARM_BACK, 0), sfx!("іп", HARM_FRONT, 0), sfx!("са", HARM_BACK, 0), sfx!("се", HARM_FRONT, 0),
    sfx!("у", HARM_ANY, 1), sfx!("й", HARM_ANY, 1), sfx!("а", HARM_BACK, 1), sfx!("е", HARM_FRONT, 1),
];

static VNEG_RULES: &[SuffixRule] = &[
    sfx!("ма", HARM_BACK, 0), sfx!("ме", HARM_FRONT, 0), sfx!("ба", HARM_BACK, 0),
    sfx!("бе", HARM_FRONT, 0), sfx!("па", HARM_BACK, 0), sfx!("пе", HARM_FRONT, 0),
];

static VVOICE_RULES: &[SuffixRule] = &[
    sfx!("қыз", HARM_BACK, 0), sfx!("кіз", HARM_FRONT, 0), sfx!("ғыз", HARM_BACK, 0), sfx!("гіз", HARM_FRONT, 0),
    sfx!("тыр", HARM_BACK, 0), sfx!("тір", HARM_FRONT, 0), sfx!("дыр", HARM_BACK, 0), sfx!("дір", HARM_FRONT, 0),
    sfx!("ыл", HARM_BACK, 0), sfx!("іл", HARM_FRONT, 0), sfx!("ыс", HARM_BACK, 0), sfx!("іс", HARM_FRONT, 0),
    sfx!("ын", HARM_BACK, 0), sfx!("ін", HARM_FRONT, 0),
];

pub static NOUN_LAYERS: &[LayerDef] = &[
    LayerDef { rules: PRED_RULES, layer_id: LAYER_PRED, repeat: false, kind: 1 },
    LayerDef { rules: CASE_RULES, layer_id: LAYER_CASE, repeat: false, kind: 1 },
    LayerDef { rules: POSS_RULES, layer_id: LAYER_POSS, repeat: false, kind: 1 },
    LayerDef { rules: PLUR_RULES, layer_id: LAYER_PLUR, repeat: false, kind: 1 },
    LayerDef { rules: DERIV_RULES, layer_id: LAYER_DERIV, repeat: true, kind: 3 },
];

pub static VERB_LAYERS: &[LayerDef] = &[
    LayerDef { rules: VPERSON_RULES, layer_id: LAYER_VPERSON, repeat: false, kind: 2 },
    LayerDef { rules: VTENSE_RULES, layer_id: LAYER_VTENSE, repeat: false, kind: 2 },
    LayerDef { rules: VNEG_RULES, layer_id: LAYER_VNEG, repeat: false, kind: 2 },
    LayerDef { rules: VVOICE_RULES, layer_id: LAYER_VVOICE, repeat: true, kind: 2 },
];

pub static POSS_VOWEL_SUFFIXES: &[&str] = &[
    "ы", "і", "сы", "сі", "ым", "ім", "ың", "ің", "ымыз", "іміз", "ыңыз", "іңіз",
];
