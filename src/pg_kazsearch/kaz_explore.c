/*
 * Layer guards, BFS suffix stripping, scoring, and stem repair for lexicon checks.
 */
#include "postgres.h"

#include "kaz_internal.h"

#define KAZ_VISIT_EMPTY UINT64_MAX

#define KAZ_SUF_MATCH(w, wlen, lit) \
	kaz_ends_with_bytes_n((w), (wlen), (lit), (int)(sizeof(lit) - 1), NULL)

/* Shortest penalty suffixes in UTF-8 bytes (3 Cyrillic letters × 2 for NIK; one letter × 2 for CONS). */
#define KAZ_PENALTY_NIK_MIN_BYTES 6
#define KAZ_PENALTY_CONS_MIN_BYTES 2

/*
 * Penalty bits for stem word[0:len). Skips NIK memcmps when len < 6; skips all when len < 2.
 */
static uint8
kaz_penalty_flags_at(const char *word, int len)
{
	uint8 f = 0;

	if (len < KAZ_PENALTY_CONS_MIN_BYTES)
		return 0;

	if (KAZ_SUF_MATCH(word, len, "д") || KAZ_SUF_MATCH(word, len, "г") ||
		KAZ_SUF_MATCH(word, len, "ғ") || KAZ_SUF_MATCH(word, len, "б"))
		f |= KAZ_PENALTY_FINAL_CONS;

	if (len < KAZ_PENALTY_NIK_MIN_BYTES)
		return f;

	if (KAZ_SUF_MATCH(word, len, "дағ") || KAZ_SUF_MATCH(word, len, "дег") ||
		KAZ_SUF_MATCH(word, len, "тағ") || KAZ_SUF_MATCH(word, len, "тег") ||
		KAZ_SUF_MATCH(word, len, "нік") || KAZ_SUF_MATCH(word, len, "дік") ||
		KAZ_SUF_MATCH(word, len, "тік"))
		f |= KAZ_PENALTY_NIK_DERIV;

	return f;
}

static void
kaz_candidate_fill_penalty_flags(KazCandidate *c, const char *word)
{
	c->penalty_flags = kaz_penalty_flags_at(word, c->len);
}

typedef struct KazVisitSet
{
	uint64_t *keys;
	int nslots;
	int64_t nused;
} KazVisitSet;

static uint64_t
kaz_visit_key(int len, int state_idx, int steps)
{
	return ((uint64_t)(uint32_t)len << 32) | ((uint64_t)(uint16_t)state_idx << 16) |
		(uint16_t)steps;
}

static void
kaz_visit_init(KazVisitSet *v, int nslots)
{
	int i;

	v->keys = palloc(sizeof(uint64_t) * nslots);
	for (i = 0; i < nslots; i++)
		v->keys[i] = KAZ_VISIT_EMPTY;
	v->nslots = nslots;
	v->nused = 0;
}

static void
kaz_visit_fini(KazVisitSet *v)
{
	if (v->keys != NULL)
	{
		pfree(v->keys);
		v->keys = NULL;
	}
}

static void
kaz_visit_grow(KazVisitSet *v)
{
	int oldslots = v->nslots;
	uint64_t *oldkeys = v->keys;
	int newslots = oldslots * 2;
	uint64_t *newkeys;
	int i;

	if (oldslots >= (1 << 20))
		ereport(ERROR,
				(errcode(ERRCODE_INTERNAL_ERROR),
				 errmsg("pg_kazsearch: visit hash overflow")));

	newkeys = palloc(sizeof(uint64_t) * newslots);
	for (i = 0; i < newslots; i++)
		newkeys[i] = KAZ_VISIT_EMPTY;

	v->keys = newkeys;
	v->nslots = newslots;
	v->nused = 0;

	for (i = 0; i < oldslots; i++)
	{
		if (oldkeys[i] != KAZ_VISIT_EMPTY)
		{
			uint64_t key = oldkeys[i];
			uint32_t h = (uint32_t)(key ^ (key >> 32));
			uint32_t slot = h & (uint32_t)(newslots - 1);
			int probe;

			for (probe = 0; probe < newslots; probe++)
			{
				uint32_t j = (slot + probe) & (uint32_t)(newslots - 1);

				if (newkeys[j] == KAZ_VISIT_EMPTY)
				{
					newkeys[j] = key;
					v->nused++;
					break;
				}
			}
		}
	}
	pfree(oldkeys);
}

/*
 * Returns true if key was already present (caller should not enqueue again).
 * Returns false if key was newly inserted.
 */
static bool
kaz_visit_seen_or_insert(KazVisitSet *v, uint64_t key)
{
	for (;;)
	{
		uint32_t h;
		uint32_t slot;
		int probe;

		if (v->nused * 3 > v->nslots * 2)
			kaz_visit_grow(v);

		h = (uint32_t)(key ^ (key >> 32));
		slot = h & (uint32_t)(v->nslots - 1);

		for (probe = 0; probe < v->nslots; probe++)
		{
			uint32_t j = (slot + probe) & (uint32_t)(v->nslots - 1);

			if (v->keys[j] == KAZ_VISIT_EMPTY)
			{
				v->keys[j] = key;
				v->nused++;
				return false;
			}
			if (v->keys[j] == key)
				return true;
		}

		kaz_visit_grow(v);
	}
}

static void
kaz_queue_push(KazExploreState **queue, int *qcap, int *qt, KazExploreState st)
{
	if (*qt >= KAZ_QUEUE_MAX)
		ereport(ERROR,
				(errcode(ERRCODE_INTERNAL_ERROR),
				 errmsg("pg_kazsearch: BFS queue overflow (max %d states)", KAZ_QUEUE_MAX)));
	if (*qt >= *qcap)
	{
		int newcap = *qcap * 2;

		if (newcap > KAZ_QUEUE_MAX)
			newcap = KAZ_QUEUE_MAX;
		if (*qt >= newcap)
			ereport(ERROR,
					(errcode(ERRCODE_INTERNAL_ERROR),
					 errmsg("pg_kazsearch: BFS queue overflow (max %d states)", KAZ_QUEUE_MAX)));
		*qcap = newcap;
		*queue = repalloc(*queue, sizeof(KazExploreState) * (*qcap));
	}
	(*queue)[(*qt)++] = st;
}

static bool
layer_guard(int layer_id, const char *sfx, const char *base, int base_len, int steps_so_far)
{
	uint32 cp;
	/* Possessive-style tails for case "а"/"е" guard; lengths from string literals (UTF-8). */
	static const struct
	{
		const char *const b;
		int len;
	} poss_tails[] = {
		{"ымыз", (int) (sizeof("ымыз") - 1)}, {"іміз", (int) (sizeof("іміз") - 1)},
		{"ыңыз", (int) (sizeof("ыңыз") - 1)}, {"іңіз", (int) (sizeof("іңіз") - 1)},
		{"мыз", (int) (sizeof("мыз") - 1)}, {"міз", (int) (sizeof("міз") - 1)},
		{"ңыз", (int) (sizeof("ңыз") - 1)}, {"ңіз", (int) (sizeof("ңіз") - 1)},
		{"ым", (int) (sizeof("ым") - 1)}, {"ім", (int) (sizeof("ім") - 1)},
		{"ың", (int) (sizeof("ың") - 1)}, {"ің", (int) (sizeof("ің") - 1)},
		{"сы", (int) (sizeof("сы") - 1)}, {"сі", (int) (sizeof("сі") - 1)},
		{"ы", (int) (sizeof("ы") - 1)}, {"і", (int) (sizeof("і") - 1)},
	};
	int pi;

	if (layer_id == KAZ_LAYER_CASE)
	{
		if (strcmp(sfx, "н") == 0)
			return KAZ_SUF_MATCH(base, base_len, "сы") || KAZ_SUF_MATCH(base, base_len, "сі") ||
				KAZ_SUF_MATCH(base, base_len, "ы") || KAZ_SUF_MATCH(base, base_len, "і");

		if (strcmp(sfx, "а") == 0 || strcmp(sfx, "е") == 0)
		{
			for (pi = 0; pi < (int) lengthof(poss_tails); pi++)
			{
				if (kaz_ends_with_bytes_n(base, base_len, poss_tails[pi].b, poss_tails[pi].len, NULL))
					return true;
			}
			if ((KAZ_SUF_MATCH(base, base_len, "м") || KAZ_SUF_MATCH(base, base_len, "ң")) && base_len > 0)
			{
				int i = 0;
				uint32 prev = 0;
				int last_start = 0;

				while (i < base_len)
				{
					last_start = i;
					if (!kaz_utf8_next_cp(base, base_len, &i, &prev))
						break;
				}
				if (last_start > 0)
				{
					int j = 0;
					uint32 cp_prev = 0;
					while (j < last_start && kaz_utf8_next_cp(base, last_start, &j, &cp_prev))
					{
					}
					return kaz_is_vowel(cp_prev);
				}
			}
			return false;
		}

		if (!kaz_utf8_last_cp(base, base_len, &cp))
			return false;

		if (strcmp(sfx, "ны") == 0 || strcmp(sfx, "ні") == 0)
			return kaz_is_vowel(cp);
		if (strcmp(sfx, "ын") == 0 || strcmp(sfx, "ін") == 0)
			return !kaz_is_vowel(cp);
		if (strcmp(sfx, "ды") == 0 || strcmp(sfx, "ді") == 0 ||
			strcmp(sfx, "ты") == 0 || strcmp(sfx, "ті") == 0)
			return !kaz_is_vowel(cp);
	}
	else if (layer_id == KAZ_LAYER_POSS)
	{
		if (strcmp(sfx, "м") == 0 || strcmp(sfx, "ң") == 0)
		{
			if (!kaz_utf8_last_cp(base, base_len, &cp))
				return false;
			return kaz_is_vowel(cp);
		}
	}
	else if (layer_id == KAZ_LAYER_VTENSE)
	{
		if (strcmp(sfx, "у") == 0)
			return kaz_utf8_char_count(base, base_len) >= 2 && kaz_count_syllables(base, base_len) >= 1;
		if (strcmp(sfx, "й") == 0)
			return steps_so_far > 0;
		if (strcmp(sfx, "а") == 0 || strcmp(sfx, "е") == 0)
			return steps_so_far > 0 && kaz_count_syllables(base, base_len) >= 2;
	}
	else if (layer_id == KAZ_LAYER_VNEG)
	{
		return kaz_utf8_char_count(base, base_len) >= 3;
	}
	else if (layer_id == KAZ_LAYER_VPERSON)
	{
		if (strcmp(sfx, "м") == 0 || strcmp(sfx, "ң") == 0 ||
			strcmp(sfx, "қ") == 0 || strcmp(sfx, "к") == 0)
			return kaz_count_syllables(base, base_len) >= 2;
	}
	else if (layer_id == KAZ_LAYER_DERIV)
	{
		if (strcmp(sfx, "лық") == 0 || strcmp(sfx, "лік") == 0 ||
			strcmp(sfx, "дық") == 0 || strcmp(sfx, "дік") == 0 ||
			strcmp(sfx, "тық") == 0 || strcmp(sfx, "тік") == 0)
			return kaz_count_syllables(base, base_len) >= 2;
	}

	return true;
}

static int
next_state_idx(bool noun_track, int cur_idx, int layer_id, const char *suffix)
{
	if (!noun_track)
	{
		if (layer_id == KAZ_LAYER_VVOICE)
			return 3;
		return cur_idx + 1;
	}

	if (layer_id == KAZ_LAYER_DERIV &&
		(strcmp(suffix, "ндағы") == 0 || strcmp(suffix, "ндегі") == 0 ||
		 strcmp(suffix, "дағы") == 0 || strcmp(suffix, "дегі") == 0 ||
		 strcmp(suffix, "тағы") == 0 || strcmp(suffix, "тегі") == 0))
		return 2;
	if (layer_id == KAZ_LAYER_DERIV)
		return 4;
	return cur_idx + 1;
}

double
kaz_candidate_penalty(const KazCandidate *c, const char *word, int original_chars, bool verb_track,
					  const int *chars_prefix, const int *syll_prefix)
{
	int chars = chars_prefix[c->len];
	int syll = syll_prefix[c->len];
	int removed = Max(0, original_chars - chars);
	double p = 0.0;

	if (c->steps == 0)
		p += 6.0;
	if (chars < 2)
		p += 120.0;
	if (syll < 1)
		p += 90.0;
	if (chars == 2)
		p += 8.0;
	if (chars == 3 && syll == 1)
		p += 2.5;

	p += c->deriv * 3.2 + c->weak * 2.5 + c->single_char * 1.2;

	if (verb_track && c->verbal_inf > 0 && c->verbal_inf == c->weak)
		p += 10.0;

	if (c->penalty_flags & KAZ_PENALTY_NIK_DERIV)
		p += 20.0;
	if (c->penalty_flags & KAZ_PENALTY_FINAL_CONS)
		p += 4.0;

	p -= c->nominal_inf * 3.9 + c->verbal_inf * 4.2 + Min(removed, 10) * 0.32;

	if (verb_track)
		p += 1.2;

	return p;
}

bool
kaz_candidate_beats(const KazCandidate *challenger, const KazCandidate *current,
					double p_challenger, double p_current, const char *word,
					const int *chars_prefix)
{
	int inf_ch, inf_cu, ch_ch, ch_cu;

	if (p_challenger != p_current)
		return p_challenger < p_current;
	if (challenger->deriv != current->deriv)
		return challenger->deriv < current->deriv;
	if (challenger->weak != current->weak)
		return challenger->weak < current->weak;

	inf_ch = challenger->nominal_inf + challenger->verbal_inf;
	inf_cu = current->nominal_inf + current->verbal_inf;
	if (inf_ch != inf_cu)
		return inf_ch > inf_cu;

	ch_ch = chars_prefix[challenger->len];
	ch_cu = chars_prefix[current->len];
	return ch_ch > ch_cu;
}

/*
 * In-place final-consonant mutation (voiced → voiceless).
 * All replacements are same byte-length in Cyrillic UTF-8.
 */
void
kaz_apply_mutation(char *lex, int len)
{
	if (len < 2)
		return;
	if (kaz_ends_with_bytes(lex, len, "б", NULL))
		memcpy(lex + len - (int) strlen("б"), "п", strlen("п"));
	else if (kaz_ends_with_bytes(lex, len, "ғ", NULL))
		memcpy(lex + len - (int) strlen("ғ"), "қ", strlen("қ"));
	else if (kaz_ends_with_bytes(lex, len, "г", NULL))
	{
		uint32 cp = 0;
		if (kaz_utf8_last_cp(lex, len - (int) strlen("г"), &cp) &&
			(cp == 0x043E || cp == 0x04E9 || cp == 0x04B1 || cp == 0x04AF || cp == 0x0443))
			return;
		memcpy(lex + len - (int) strlen("г"), "к", strlen("к"));
	}
}

/*
 * Restore elided vowel before a final н/з when a consonant cluster
 * or a уз/із ending is detected.  Returns the (possibly reallocated) stem.
 */
char *
kaz_apply_elision_restore(char *lex, int len)
{
	int i = 0;
	int last_start = 0;
	uint32 cp = 0;
	uint32 prev_cp = 0;
	uint32 last_vowel = 0;
	bool have_prev = false;

	while (i < len)
	{
		int start = i;
		if (!kaz_utf8_next_cp(lex, len, &i, &cp))
			return lex;
		if (kaz_is_vowel(cp))
			last_vowel = cp;
		prev_cp = cp;
		have_prev = true;
		last_start = start;
	}
	if (!have_prev)
		return lex;
	if (!(cp == 0x043D || cp == 0x0437)) /* н or з */
		return lex;
	if (last_start <= 0)
		return lex;

	i = 0;
	have_prev = false;
	while (i < last_start)
	{
		if (!kaz_utf8_next_cp(lex, last_start, &i, &prev_cp))
			return lex;
		have_prev = true;
	}
	if (!have_prev)
		return lex;

	/* Consonant cluster, or уз/із ending (vowel + з) */
	if (kaz_is_vowel(prev_cp))
	{
		if (!kaz_ends_with_bytes(lex, len, "уз", NULL) &&
			!kaz_ends_with_bytes(lex, len, "із", NULL))
			return lex;
	}

	if (!last_vowel)
		return lex;

	{
		const char *ins = kaz_is_back_vowel(last_vowel) ? "ы" : "і";
		int ins_len = (int) strlen(ins);
		char *out = palloc(len + ins_len + 1);
		memcpy(out, lex, last_start);
		memcpy(out + last_start, ins, ins_len);
		memcpy(out + last_start + ins_len, lex + last_start, len - last_start + 1);
		pfree(lex);
		return out;
	}
}

static bool
try_elision_restore_buf(char *lex, int *len, int cap)
{
	int i = 0;
	int last_start = 0;
	uint32 cp = 0;
	uint32 prev_cp = 0;
	uint32 last_vowel = 0;
	bool have_prev = false;
	const char *ins;
	int ins_len;

	while (i < *len)
	{
		int start = i;
		if (!kaz_utf8_next_cp(lex, *len, &i, &cp))
			return false;
		if (kaz_is_vowel(cp))
			last_vowel = cp;
		prev_cp = cp;
		have_prev = true;
		last_start = start;
	}
	if (!have_prev)
		return false;
	if (!(cp == 0x043D || cp == 0x0437)) /* н or з */
		return false;
	if (last_start <= 0)
		return false;

	i = 0;
	have_prev = false;
	while (i < last_start)
	{
		if (!kaz_utf8_next_cp(lex, last_start, &i, &prev_cp))
			return false;
		have_prev = true;
	}
	if (!have_prev)
		return false;
	if (kaz_is_vowel(prev_cp) &&
		!kaz_ends_with_bytes(lex, *len, "уз", NULL) &&
		!kaz_ends_with_bytes(lex, *len, "із", NULL))
		return false;
	if (!last_vowel)
		return false;

	ins = kaz_is_back_vowel(last_vowel) ? "ы" : "і";
	ins_len = (int) strlen(ins);
	if (*len + ins_len >= cap)
		return false;

	memmove(lex + last_start + ins_len, lex + last_start, *len - last_start + 1);
	memcpy(lex + last_start, ins, ins_len);
	*len += ins_len;
	return true;
}

static bool
try_append_vowel_check(const char *stem, int len, const char *suffix, HTAB *lexicon)
{
	char trial[KAZ_MAX_STEM_BYTES];
	int suffix_len = (int) strlen(suffix);

	if (len <= 0 || len + suffix_len >= KAZ_MAX_STEM_BYTES)
		return false;

	memcpy(trial, stem, len);
	memcpy(trial + len, suffix, suffix_len);
	trial[len + suffix_len] = '\0';
	return kaz_lexicon_contains(lexicon, trial, len + suffix_len);
}

bool
kaz_candidate_hits_lexicon(const KazCandidate *c, const char *word, HTAB *lexicon)
{
	char stem[KAZ_MAX_STEM_BYTES];
	char alt[KAZ_MAX_STEM_BYTES];
	int len;
	int alt_len;
	uint32 last_cp = 0;
	bool stem_back;
	const char *v1;
	const char *v2;

	if (lexicon == NULL)
		return false;
	if (c->len <= 0 || c->len >= KAZ_MAX_STEM_BYTES)
		return false;

	memcpy(stem, word, c->len);
	stem[c->len] = '\0';
	len = c->len;
	if (kaz_lexicon_contains(lexicon, stem, len))
		return true;

	if (c->steps > 0 && c->nominal_inf > 0 && c->last_suffix &&
		kaz_suffix_in(c->last_suffix, kaz_poss_vowel_suffixes, kaz_poss_vowel_suffix_count))
	{
		memcpy(alt, stem, len + 1);
		alt_len = len;
		kaz_apply_mutation(alt, alt_len);
		if (kaz_lexicon_contains(lexicon, alt, alt_len))
			return true;
		if (try_elision_restore_buf(alt, &alt_len, KAZ_MAX_STEM_BYTES) &&
			kaz_lexicon_contains(lexicon, alt, alt_len))
			return true;

		memcpy(alt, stem, len + 1);
		alt_len = len;
		if (try_elision_restore_buf(alt, &alt_len, KAZ_MAX_STEM_BYTES))
		{
			if (kaz_lexicon_contains(lexicon, alt, alt_len))
				return true;
			kaz_apply_mutation(alt, alt_len);
			if (kaz_lexicon_contains(lexicon, alt, alt_len))
				return true;
		}
	}

	if (c->steps < 2 || !kaz_utf8_last_cp(stem, len, &last_cp) || kaz_is_vowel(last_cp))
		return false;

	stem_back = kaz_word_is_back(stem, len);
	v1 = stem_back ? "ы" : "і";
	v2 = stem_back ? "а" : "е";
	if (try_append_vowel_check(stem, len, v1, lexicon))
		return true;
	if (try_append_vowel_check(stem, len, v2, lexicon))
		return true;

	memcpy(alt, stem, len + 1);
	alt_len = len;
	kaz_apply_mutation(alt, alt_len);
	if (try_append_vowel_check(alt, alt_len, v1, lexicon))
		return true;
	if (try_append_vowel_check(alt, alt_len, v2, lexicon))
		return true;

	return false;
}

KazExploreResult
kaz_explore_track_best(const char *word, int len, const KazLayerDef *layers, int nlayer,
					   const KazStemCfg *cfg, bool noun_track,
					   const int *chars_prefix, const int *syll_prefix)
{
	KazExploreState *queue;
	KazVisitSet visit;
	int qh = 0;
	int qt = 0;
	int qcap = KAZ_QUEUE_INIT;
	KazExploreResult result;
	double best_pen;
	double best_lex_pen = 0.0;
	int original_chars = chars_prefix[len];
	bool verb_track = !noun_track;

	queue = palloc(sizeof(KazExploreState) * qcap);
	kaz_visit_init(&visit, KAZ_VISIT_HASH_INIT);

	MemSet(&result, 0, sizeof(result));
	result.best_scored.len = len;
	kaz_candidate_fill_penalty_flags(&result.best_scored, word);
	best_pen = kaz_candidate_penalty(&result.best_scored, word, original_chars, verb_track,
									 chars_prefix, syll_prefix);

	{
		KazExploreState seed;

		kaz_visit_seen_or_insert(&visit, kaz_visit_key(len, 0, 0));
		seed.len = len;
		seed.state_idx = 0;
		MemSet(&seed.c, 0, sizeof(seed.c));
		seed.c.len = len;
		kaz_candidate_fill_penalty_flags(&seed.c, word);
		kaz_queue_push(&queue, &qcap, &qt, seed);
	}

	while (qh < qt)
	{
		KazExploreState st = queue[qh++];
		const KazLayerDef *layer;
		int i;

		{
			double cur_pen = kaz_candidate_penalty(&st.c, word, original_chars, verb_track,
												   chars_prefix, syll_prefix);

			if (kaz_candidate_beats(&st.c, &result.best_scored, cur_pen, best_pen, word,
									  chars_prefix))
			{
				result.best_scored = st.c;
				best_pen = cur_pen;
			}

			if (st.c.steps > 0 && kaz_candidate_hits_lexicon(&st.c, word, cfg->lexicon))
			{
				if (!result.has_lexhit ||
					kaz_candidate_beats(&st.c, &result.best_lexhit, cur_pen, best_lex_pen, word,
										chars_prefix))
				{
					result.best_lexhit = st.c;
					best_lex_pen = cur_pen;
					result.has_lexhit = true;
				}
			}
		}

		if (st.state_idx >= nlayer || st.c.steps >= cfg->max_steps)
			continue;

		/* Option 1: skip current layer */
		{
			KazExploreState next = st;

			next.state_idx = st.state_idx + 1;
			if (!kaz_visit_seen_or_insert(&visit, kaz_visit_key(next.len, next.state_idx, next.c.steps)))
				kaz_queue_push(&queue, &qcap, &qt, next);
		}

		layer = &layers[st.state_idx];
		if (!cfg->derivation && layer->layer_id == KAZ_LAYER_DERIV)
			continue;

		/* Option 2: strip a matching suffix */
		for (i = 0; i < layer->count; i++)
		{
			const KazSuffixRule *rule = &layer->rules[i];
			int base_len = 0;
			KazExploreState next;
			int sfx_chars;

			if (!kaz_ends_with_bytes_n(word, st.len, rule->suffix, rule->suffix_len, &base_len))
				continue;
			if (chars_prefix[base_len] < 2)
				continue;
			if (syll_prefix[base_len] < 1)
				continue;
			if (!kaz_harmony_ok(word, base_len, rule->harmony))
				continue;
			if (!layer_guard(layer->layer_id, rule->suffix, word, base_len, st.c.steps))
				continue;

			next = st;
			next.len = base_len;
			next.c.len = base_len;
			next.c.steps++;
			next.c.last_suffix = rule->suffix;
			next.c.last_layer = layer->layer_id;
			next.c.weak += rule->weak ? 1 : 0;
			sfx_chars = kaz_utf8_char_count(rule->suffix, (int) rule->suffix_len);
			kaz_candidate_fill_penalty_flags(&next.c, word);
			if (sfx_chars == 1)
				next.c.single_char++;
			if (layer->kind == 1)
				next.c.nominal_inf++;
			else if (layer->kind == 2)
				next.c.verbal_inf++;
			else
				next.c.deriv++;
			next.state_idx = next_state_idx(noun_track, st.state_idx, layer->layer_id, rule->suffix);

			if (!kaz_visit_seen_or_insert(&visit, kaz_visit_key(next.len, next.state_idx, next.c.steps)))
				kaz_queue_push(&queue, &qcap, &qt, next);
		}
	}

	pfree(queue);
	kaz_visit_fini(&visit);

	return result;
}
