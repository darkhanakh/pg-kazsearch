/*
 * Shared types and internal API for pg_kazsearch stemmer.
 * Not a public installed header — used only by extension sources.
 */
#ifndef KAZ_INTERNAL_H
#define KAZ_INTERNAL_H

#include "postgres.h"

#include "utils/hsearch.h"

/* Limits */
#define KAZ_QUEUE_INIT 1024
#define KAZ_QUEUE_MAX (1 << 18)	/* 256k states; overflow is an error */
#define KAZ_VISIT_HASH_INIT 4096
#define KAZ_MAX_STEM_BYTES 128

/* Penalty-weight defaults (compile-time; overridable via dictionary options) */
#define KAZ_DEFAULT_W_NO_STRIP      6.0
#define KAZ_DEFAULT_W_SHORT_CHAR  120.0
#define KAZ_DEFAULT_W_NO_SYLL      90.0
#define KAZ_DEFAULT_W_TWO_CHAR      8.0
#define KAZ_DEFAULT_W_THREE_ONE     2.5
#define KAZ_DEFAULT_W_DERIV         3.2
#define KAZ_DEFAULT_W_WEAK          2.5
#define KAZ_DEFAULT_W_SINGLE_CHAR   1.2
#define KAZ_DEFAULT_W_VERB_ALL_WEAK 10.0
#define KAZ_DEFAULT_W_NIK_DERIV    20.0
#define KAZ_DEFAULT_W_FINAL_CONS    4.0
#define KAZ_DEFAULT_W_NOMINAL_INF   3.9
#define KAZ_DEFAULT_W_VERBAL_INF    4.2
#define KAZ_DEFAULT_W_REMOVED       0.32
#define KAZ_DEFAULT_W_VERB_TRACK    1.2

enum
{
	KAZ_HARM_ANY = 0,
	KAZ_HARM_BACK = 1,
	KAZ_HARM_FRONT = 2,
};

enum
{
	KAZ_LAYER_PRED = 1,
	KAZ_LAYER_CASE = 2,
	KAZ_LAYER_POSS = 3,
	KAZ_LAYER_PLUR = 4,
	KAZ_LAYER_DERIV = 5,
	KAZ_LAYER_VPERSON = 11,
	KAZ_LAYER_VTENSE = 12,
	KAZ_LAYER_VNEG = 13,
	KAZ_LAYER_VVOICE = 14,
};

typedef struct KazPenaltyWeights
{
	double w_no_strip;
	double w_short_char;
	double w_no_syll;
	double w_two_char;
	double w_three_one;
	double w_deriv;
	double w_weak;
	double w_single_char;
	double w_verb_all_weak;
	double w_nik_deriv;
	double w_final_cons;
	double w_nominal_inf;
	double w_verbal_inf;
	double w_removed;
	double w_verb_track;
} KazPenaltyWeights;

typedef struct KazStemCfg
{
	bool derivation;
	int32 max_steps;
	HTAB *lexicon;
	KazPenaltyWeights weights;
} KazStemCfg;

typedef struct KazSuffixRule
{
	const char *suffix;
	uint8 suffix_len; /* UTF-8 byte length; avoids strlen in strip loop */
	uint8 harmony; /* KAZ_HARM_ANY / BACK / FRONT */
	uint8 weak;
} KazSuffixRule;

typedef struct KazCandidate
{
	int len;
	int steps;
	int nominal_inf;
	int verbal_inf;
	int deriv;
	int weak;
	int single_char;
	uint8 penalty_flags; /* KAZ_PENALTY_* — suffix checks for scoring */
	const char *last_suffix;
	int last_layer;
} KazCandidate;

#define KAZ_PENALTY_NIK_DERIV 1 /* дағ/дег/…/тік */
#define KAZ_PENALTY_FINAL_CONS 2 /* д/г/ғ/б */

typedef struct KazLayerDef
{
	const KazSuffixRule *rules;
	int count;
	int layer_id;
	bool repeat;
	int kind; /* 1=nominal_inf, 2=verbal_inf, 3=deriv */
} KazLayerDef;

typedef struct KazExploreState
{
	int len;
	int state_idx;
	KazCandidate c;
} KazExploreState;

typedef struct KazExploreResult
{
	KazCandidate best_scored;
	KazCandidate best_lexhit;
	bool has_lexhit;
} KazExploreResult;

typedef struct KazLexiconEntry
{
	char key[KAZ_MAX_STEM_BYTES];
} KazLexiconEntry;

/* kaz_rules.c */
extern const KazLayerDef kaz_noun_layers[];
extern const int kaz_noun_layer_count;
extern const KazLayerDef kaz_verb_layers[];
extern const int kaz_verb_layer_count;
extern const char *const kaz_poss_vowel_suffixes[];
extern const int kaz_poss_vowel_suffix_count;

/* kaz_text.c */
extern bool kaz_utf8_next_cp(const char *s, int len, int *idx, uint32 *cp);
extern bool kaz_utf8_last_cp(const char *s, int len, uint32 *cp);
extern int kaz_utf8_char_count(const char *s, int len);
extern bool kaz_is_back_vowel(uint32 cp);
extern bool kaz_is_front_vowel(uint32 cp);
extern bool kaz_is_vowel(uint32 cp);
extern bool kaz_is_glide(uint32 cp);
extern int kaz_count_syllables(const char *s, int len);
extern void kaz_fill_prefix_tables(const char *word, int len, int *chars_prefix, int *syll_prefix);
extern bool kaz_word_is_back(const char *s, int len);
extern bool kaz_harmony_ok(const char *s, int len, uint8 harmony);
extern bool kaz_ends_with_bytes_n(const char *s, int len, const char *suffix, int suffix_len,
								  int *base_len);
extern bool kaz_ends_with_bytes(const char *s, int len, const char *suffix, int *base_len);
extern bool kaz_ends_with_any_n(const char *s, int len, const char *const *suffixes,
								const int *suffix_lens, int n);
extern bool kaz_ends_with_any(const char *s, int len, const char *const *suffixes, int n);
extern bool kaz_suffix_in(const char *sfx, const char *const *arr, int n);

/* kaz_lexicon.c */
extern HTAB *kaz_load_lexicon_table(const char *lexicon_name);
extern bool kaz_lexicon_contains(HTAB *lexicon, const char *word, int len);

/* kaz_explore.c */
extern KazExploreResult kaz_explore_track_best(const char *word, int len,
											   const KazLayerDef *layers, int nlayer,
											   const KazStemCfg *cfg, bool noun_track,
											   const int *chars_prefix, const int *syll_prefix);
extern bool kaz_candidate_hits_lexicon(const KazCandidate *c, const char *word, HTAB *lexicon);
extern double kaz_candidate_penalty(const KazCandidate *c, const char *word, int original_chars,
									bool verb_track,
									const int *chars_prefix, const int *syll_prefix,
									const KazPenaltyWeights *w);
extern bool kaz_candidate_beats(const KazCandidate *challenger, const KazCandidate *current,
								double p_challenger, double p_current, const char *word,
								const int *chars_prefix);
extern void kaz_apply_mutation(char *lex, int len);
extern char *kaz_apply_elision_restore(char *lex, int len);

#endif							/* KAZ_INTERNAL_H */
