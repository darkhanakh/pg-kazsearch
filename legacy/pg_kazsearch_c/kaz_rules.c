/*
 * Suffix rule tables for Kazakh nominal and verbal layer stacks.
 */
#include "postgres.h"

#include "kaz_internal.h"

/* String literal sizeof includes '\0'; suffix_len is UTF-8 byte count. */
#define KAZ_SFX(str, harm, weak) {(str), (uint8)(sizeof(str) - 1), (harm), (weak)}


static const KazSuffixRule kaz_pred_rules[] = {
	KAZ_SFX("сыңдар", KAZ_HARM_ANY, 0), KAZ_SFX("сіңдер", KAZ_HARM_ANY, 0), KAZ_SFX("сыздар", KAZ_HARM_ANY, 0), KAZ_SFX("сіздер", KAZ_HARM_ANY, 0),
	KAZ_SFX("сыз", KAZ_HARM_BACK, 0), KAZ_SFX("сіз", KAZ_HARM_FRONT, 0), KAZ_SFX("сың", KAZ_HARM_BACK, 0), KAZ_SFX("сің", KAZ_HARM_FRONT, 0),
	KAZ_SFX("мын", KAZ_HARM_BACK, 0), KAZ_SFX("мін", KAZ_HARM_FRONT, 0), KAZ_SFX("бын", KAZ_HARM_BACK, 0), KAZ_SFX("бін", KAZ_HARM_FRONT, 0),
	KAZ_SFX("пын", KAZ_HARM_BACK, 0), KAZ_SFX("пін", KAZ_HARM_FRONT, 0), KAZ_SFX("мыз", KAZ_HARM_BACK, 0), KAZ_SFX("міз", KAZ_HARM_FRONT, 0),
};

static const KazSuffixRule kaz_case_rules[] = {
	KAZ_SFX("ның", KAZ_HARM_BACK, 0), KAZ_SFX("нің", KAZ_HARM_FRONT, 0), KAZ_SFX("дың", KAZ_HARM_BACK, 0),
	KAZ_SFX("дің", KAZ_HARM_FRONT, 0), KAZ_SFX("тың", KAZ_HARM_BACK, 0), KAZ_SFX("тің", KAZ_HARM_FRONT, 0), KAZ_SFX("нан", KAZ_HARM_BACK, 0),
	KAZ_SFX("нен", KAZ_HARM_FRONT, 0), KAZ_SFX("дан", KAZ_HARM_BACK, 0), KAZ_SFX("ден", KAZ_HARM_FRONT, 0), KAZ_SFX("тан", KAZ_HARM_BACK, 0),
	KAZ_SFX("тен", KAZ_HARM_FRONT, 0), KAZ_SFX("нда", KAZ_HARM_BACK, 0), KAZ_SFX("нде", KAZ_HARM_FRONT, 0), KAZ_SFX("бен", KAZ_HARM_ANY, 0),
	KAZ_SFX("пен", KAZ_HARM_ANY, 0), KAZ_SFX("мен", KAZ_HARM_ANY, 0), KAZ_SFX("ға", KAZ_HARM_BACK, 0), KAZ_SFX("ге", KAZ_HARM_FRONT, 0),
	KAZ_SFX("қа", KAZ_HARM_BACK, 0), KAZ_SFX("ке", KAZ_HARM_FRONT, 0), KAZ_SFX("на", KAZ_HARM_BACK, 0), KAZ_SFX("не", KAZ_HARM_FRONT, 0),
	KAZ_SFX("ңа", KAZ_HARM_BACK, 0), KAZ_SFX("ңе", KAZ_HARM_FRONT, 0), KAZ_SFX("ны", KAZ_HARM_BACK, 0), KAZ_SFX("ні", KAZ_HARM_FRONT, 0),
	KAZ_SFX("а", KAZ_HARM_BACK, 1), KAZ_SFX("е", KAZ_HARM_FRONT, 1), KAZ_SFX("ды", KAZ_HARM_BACK, 0), KAZ_SFX("ді", KAZ_HARM_FRONT, 0), KAZ_SFX("ты", KAZ_HARM_BACK, 0), KAZ_SFX("ті", KAZ_HARM_FRONT, 0),
	KAZ_SFX("ын", KAZ_HARM_BACK, 0), KAZ_SFX("ін", KAZ_HARM_FRONT, 0), KAZ_SFX("да", KAZ_HARM_BACK, 0), KAZ_SFX("де", KAZ_HARM_FRONT, 0),
	KAZ_SFX("та", KAZ_HARM_BACK, 0), KAZ_SFX("те", KAZ_HARM_FRONT, 0), KAZ_SFX("н", KAZ_HARM_ANY, 1),
};

static const KazSuffixRule kaz_poss_rules[] = {
	KAZ_SFX("ымыз", KAZ_HARM_BACK, 0), KAZ_SFX("іміз", KAZ_HARM_FRONT, 0), KAZ_SFX("ыңыз", KAZ_HARM_BACK, 0), KAZ_SFX("іңіз", KAZ_HARM_FRONT, 0),
	KAZ_SFX("лары", KAZ_HARM_BACK, 0), KAZ_SFX("лері", KAZ_HARM_FRONT, 0), KAZ_SFX("дары", KAZ_HARM_BACK, 0), KAZ_SFX("дері", KAZ_HARM_FRONT, 0),
	KAZ_SFX("тары", KAZ_HARM_BACK, 0), KAZ_SFX("тері", KAZ_HARM_FRONT, 0), KAZ_SFX("мыз", KAZ_HARM_BACK, 0), KAZ_SFX("міз", KAZ_HARM_FRONT, 0),
	KAZ_SFX("ңыз", KAZ_HARM_BACK, 0), KAZ_SFX("ңіз", KAZ_HARM_FRONT, 0), KAZ_SFX("сы", KAZ_HARM_BACK, 1), KAZ_SFX("сі", KAZ_HARM_FRONT, 1),
	KAZ_SFX("ым", KAZ_HARM_BACK, 0), KAZ_SFX("ім", KAZ_HARM_FRONT, 0), KAZ_SFX("ың", KAZ_HARM_BACK, 0), KAZ_SFX("ің", KAZ_HARM_FRONT, 0),
	KAZ_SFX("ы", KAZ_HARM_BACK, 1), KAZ_SFX("і", KAZ_HARM_FRONT, 1), KAZ_SFX("м", KAZ_HARM_ANY, 1), KAZ_SFX("ң", KAZ_HARM_ANY, 1),
};

static const KazSuffixRule kaz_plur_rules[] = {
	KAZ_SFX("дар", KAZ_HARM_BACK, 0), KAZ_SFX("дер", KAZ_HARM_FRONT, 0), KAZ_SFX("лар", KAZ_HARM_BACK, 0),
	KAZ_SFX("лер", KAZ_HARM_FRONT, 0), KAZ_SFX("тар", KAZ_HARM_BACK, 0), KAZ_SFX("тер", KAZ_HARM_FRONT, 0),
};

static const KazSuffixRule kaz_deriv_rules[] = {
	KAZ_SFX("ндағы", KAZ_HARM_BACK, 0), KAZ_SFX("ндегі", KAZ_HARM_FRONT, 0), KAZ_SFX("дағы", KAZ_HARM_BACK, 0), KAZ_SFX("дегі", KAZ_HARM_FRONT, 0),
	KAZ_SFX("тағы", KAZ_HARM_BACK, 0), KAZ_SFX("тегі", KAZ_HARM_FRONT, 0), KAZ_SFX("нікі", KAZ_HARM_ANY, 1), KAZ_SFX("дікі", KAZ_HARM_ANY, 1),
	KAZ_SFX("тікі", KAZ_HARM_ANY, 1),
	KAZ_SFX("ырақ", KAZ_HARM_BACK, 0), KAZ_SFX("ірек", KAZ_HARM_FRONT, 0), KAZ_SFX("рақ", KAZ_HARM_BACK, 0), KAZ_SFX("рек", KAZ_HARM_FRONT, 0),
	KAZ_SFX("лау", KAZ_HARM_BACK, 0), KAZ_SFX("леу", KAZ_HARM_FRONT, 0), KAZ_SFX("дау", KAZ_HARM_BACK, 0), KAZ_SFX("деу", KAZ_HARM_FRONT, 0),
	KAZ_SFX("тау", KAZ_HARM_BACK, 0), KAZ_SFX("теу", KAZ_HARM_FRONT, 0), KAZ_SFX("лық", KAZ_HARM_BACK, 0), KAZ_SFX("лік", KAZ_HARM_FRONT, 0),
	KAZ_SFX("дық", KAZ_HARM_BACK, 0), KAZ_SFX("дік", KAZ_HARM_FRONT, 0), KAZ_SFX("тық", KAZ_HARM_BACK, 0), KAZ_SFX("тік", KAZ_HARM_FRONT, 0),
	KAZ_SFX("шы", KAZ_HARM_BACK, 1), KAZ_SFX("ші", KAZ_HARM_FRONT, 1), KAZ_SFX("ша", KAZ_HARM_BACK, 1), KAZ_SFX("ше", KAZ_HARM_FRONT, 1),
	KAZ_SFX("сыз", KAZ_HARM_BACK, 0), KAZ_SFX("сіз", KAZ_HARM_FRONT, 0), KAZ_SFX("ғы", KAZ_HARM_BACK, 1), KAZ_SFX("гі", KAZ_HARM_FRONT, 1),
	KAZ_SFX("ншы", KAZ_HARM_BACK, 0), KAZ_SFX("нші", KAZ_HARM_FRONT, 0), KAZ_SFX("дай", KAZ_HARM_BACK, 0), KAZ_SFX("дей", KAZ_HARM_FRONT, 0),
	KAZ_SFX("тай", KAZ_HARM_BACK, 0), KAZ_SFX("тей", KAZ_HARM_FRONT, 0), KAZ_SFX("ба", KAZ_HARM_BACK, 1), KAZ_SFX("бе", KAZ_HARM_FRONT, 1),
};

static const KazSuffixRule kaz_vperson_rules[] = {
	KAZ_SFX("сыңдар", KAZ_HARM_ANY, 0), KAZ_SFX("сіңдер", KAZ_HARM_ANY, 0), KAZ_SFX("сыздар", KAZ_HARM_BACK, 0), KAZ_SFX("сіздер", KAZ_HARM_FRONT, 0),
	KAZ_SFX("мыз", KAZ_HARM_BACK, 0), KAZ_SFX("міз", KAZ_HARM_FRONT, 0), KAZ_SFX("сыз", KAZ_HARM_BACK, 0), KAZ_SFX("сіз", KAZ_HARM_FRONT, 0),
	KAZ_SFX("сың", KAZ_HARM_BACK, 0), KAZ_SFX("сің", KAZ_HARM_FRONT, 0), KAZ_SFX("мын", KAZ_HARM_BACK, 0), KAZ_SFX("мін", KAZ_HARM_FRONT, 0),
	KAZ_SFX("бын", KAZ_HARM_BACK, 0), KAZ_SFX("бін", KAZ_HARM_FRONT, 0), KAZ_SFX("пын", KAZ_HARM_BACK, 0), KAZ_SFX("пін", KAZ_HARM_FRONT, 0),
	KAZ_SFX("м", KAZ_HARM_ANY, 1), KAZ_SFX("ң", KAZ_HARM_ANY, 1), KAZ_SFX("қ", KAZ_HARM_BACK, 1), KAZ_SFX("к", KAZ_HARM_FRONT, 1),
};

static const KazSuffixRule kaz_vtense_rules[] = {
	KAZ_SFX("майды", KAZ_HARM_BACK, 0), KAZ_SFX("мейді", KAZ_HARM_FRONT, 0), KAZ_SFX("байды", KAZ_HARM_BACK, 0), KAZ_SFX("бейді", KAZ_HARM_FRONT, 0),
	KAZ_SFX("пайды", KAZ_HARM_BACK, 0), KAZ_SFX("пейді", KAZ_HARM_FRONT, 0), KAZ_SFX("атын", KAZ_HARM_BACK, 0), KAZ_SFX("етін", KAZ_HARM_FRONT, 0),
	KAZ_SFX("йтын", KAZ_HARM_BACK, 0), KAZ_SFX("йтін", KAZ_HARM_FRONT, 0), KAZ_SFX("ыпты", KAZ_HARM_BACK, 0), KAZ_SFX("іпті", KAZ_HARM_FRONT, 0),
	KAZ_SFX("пты", KAZ_HARM_BACK, 0), KAZ_SFX("пті", KAZ_HARM_FRONT, 0), KAZ_SFX("йды", KAZ_HARM_ANY, 0), KAZ_SFX("йді", KAZ_HARM_ANY, 0),
	KAZ_SFX("ады", KAZ_HARM_BACK, 0), KAZ_SFX("еді", KAZ_HARM_FRONT, 0), KAZ_SFX("ған", KAZ_HARM_BACK, 0), KAZ_SFX("ген", KAZ_HARM_FRONT, 0),
	KAZ_SFX("қан", KAZ_HARM_BACK, 0), KAZ_SFX("кен", KAZ_HARM_FRONT, 0), KAZ_SFX("май", KAZ_HARM_BACK, 0), KAZ_SFX("мей", KAZ_HARM_FRONT, 0),
	KAZ_SFX("саң", KAZ_HARM_BACK, 0), KAZ_SFX("сең", KAZ_HARM_FRONT, 0), KAZ_SFX("сақ", KAZ_HARM_BACK, 0), KAZ_SFX("сек", KAZ_HARM_FRONT, 0),
	KAZ_SFX("тын", KAZ_HARM_BACK, 0), KAZ_SFX("тін", KAZ_HARM_FRONT, 0), KAZ_SFX("мақ", KAZ_HARM_BACK, 0), KAZ_SFX("мек", KAZ_HARM_FRONT, 0),
	KAZ_SFX("бақ", KAZ_HARM_BACK, 0), KAZ_SFX("бек", KAZ_HARM_FRONT, 0), KAZ_SFX("пақ", KAZ_HARM_BACK, 0), KAZ_SFX("пек", KAZ_HARM_FRONT, 0),
	KAZ_SFX("ды", KAZ_HARM_BACK, 0), KAZ_SFX("ді", KAZ_HARM_FRONT, 0), KAZ_SFX("ты", KAZ_HARM_BACK, 0), KAZ_SFX("ті", KAZ_HARM_FRONT, 0),
	KAZ_SFX("ып", KAZ_HARM_BACK, 0), KAZ_SFX("іп", KAZ_HARM_FRONT, 0), KAZ_SFX("са", KAZ_HARM_BACK, 0), KAZ_SFX("се", KAZ_HARM_FRONT, 0),
	KAZ_SFX("у", KAZ_HARM_ANY, 1), KAZ_SFX("й", KAZ_HARM_ANY, 1), KAZ_SFX("а", KAZ_HARM_BACK, 1), KAZ_SFX("е", KAZ_HARM_FRONT, 1),
};

static const KazSuffixRule kaz_vneg_rules[] = {
	KAZ_SFX("ма", KAZ_HARM_BACK, 0), KAZ_SFX("ме", KAZ_HARM_FRONT, 0), KAZ_SFX("ба", KAZ_HARM_BACK, 0),
	KAZ_SFX("бе", KAZ_HARM_FRONT, 0), KAZ_SFX("па", KAZ_HARM_BACK, 0), KAZ_SFX("пе", KAZ_HARM_FRONT, 0),
};

static const KazSuffixRule kaz_vvoice_rules[] = {
	KAZ_SFX("қыз", KAZ_HARM_BACK, 0), KAZ_SFX("кіз", KAZ_HARM_FRONT, 0), KAZ_SFX("ғыз", KAZ_HARM_BACK, 0), KAZ_SFX("гіз", KAZ_HARM_FRONT, 0),
	KAZ_SFX("тыр", KAZ_HARM_BACK, 0), KAZ_SFX("тір", KAZ_HARM_FRONT, 0), KAZ_SFX("дыр", KAZ_HARM_BACK, 0), KAZ_SFX("дір", KAZ_HARM_FRONT, 0),
	KAZ_SFX("ыл", KAZ_HARM_BACK, 0), KAZ_SFX("іл", KAZ_HARM_FRONT, 0), KAZ_SFX("ыс", KAZ_HARM_BACK, 0), KAZ_SFX("іс", KAZ_HARM_FRONT, 0),
	KAZ_SFX("ын", KAZ_HARM_BACK, 0), KAZ_SFX("ін", KAZ_HARM_FRONT, 0),
};

const KazLayerDef kaz_noun_layers[] = {
	{kaz_pred_rules, lengthof(kaz_pred_rules), KAZ_LAYER_PRED, false, 1},
	{kaz_case_rules, lengthof(kaz_case_rules), KAZ_LAYER_CASE, false, 1},
	{kaz_poss_rules, lengthof(kaz_poss_rules), KAZ_LAYER_POSS, false, 1},
	{kaz_plur_rules, lengthof(kaz_plur_rules), KAZ_LAYER_PLUR, false, 1},
	{kaz_deriv_rules, lengthof(kaz_deriv_rules), KAZ_LAYER_DERIV, true, 3},
};

const int kaz_noun_layer_count = lengthof(kaz_noun_layers);

const KazLayerDef kaz_verb_layers[] = {
	{kaz_vperson_rules, lengthof(kaz_vperson_rules), KAZ_LAYER_VPERSON, false, 2},
	{kaz_vtense_rules, lengthof(kaz_vtense_rules), KAZ_LAYER_VTENSE, false, 2},
	{kaz_vneg_rules, lengthof(kaz_vneg_rules), KAZ_LAYER_VNEG, false, 2},
	{kaz_vvoice_rules, lengthof(kaz_vvoice_rules), KAZ_LAYER_VVOICE, true, 2},
};

const int kaz_verb_layer_count = lengthof(kaz_verb_layers);

/* Possessive suffixes that trigger stem repair */
const char *const kaz_poss_vowel_suffixes[] = {
	"ы", "і", "сы", "сі", "ым", "ім", "ың", "ің", "ымыз", "іміз", "ыңыз", "іңіз"
};

const int kaz_poss_vowel_suffix_count = lengthof(kaz_poss_vowel_suffixes);
