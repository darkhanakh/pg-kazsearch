/*
 * PostgreSQL text search dictionary: INIT / LEXIZE entry points.
 */
#include "postgres.h"
#include "fmgr.h"

#include "catalog/pg_collation_d.h"
#include "commands/defrem.h"
#include "tsearch/ts_public.h"
#include "utils/builtins.h"
#include "utils/formatting.h"

#include "kaz_internal.h"

PG_MODULE_MAGIC;

PG_FUNCTION_INFO_V1(pg_kazsearch_init);
PG_FUNCTION_INFO_V1(pg_kazsearch_lexize);

static const char *const kaz_exceptions[] = {};

static bool
kaz_is_exception(const char *word, int len)
{
	int i;
	for (i = 0; i < (int) lengthof(kaz_exceptions); i++)
	{
		int elen = (int) strlen(kaz_exceptions[i]);
		if (len == elen && memcmp(word, kaz_exceptions[i], len) == 0)
			return true;
	}
	return false;
}

static char *
kaz_restore_lexicon_vowel(char *lexeme, HTAB *lexicon, int steps)
{
	int len;
	uint32 cp = 0;
	bool is_back;
	const char *v;
	char trial[KAZ_MAX_STEM_BYTES];
	int vlen;

	if (lexicon == NULL || steps < 2)
		return lexeme;
	len = (int) strlen(lexeme);
	if (len <= 0 || len >= KAZ_MAX_STEM_BYTES)
		return lexeme;
	if (!kaz_utf8_last_cp(lexeme, len, &cp) || kaz_is_vowel(cp))
		return lexeme;

	is_back = kaz_word_is_back(lexeme, len);

	v = is_back ? "ы" : "і";
	vlen = (int) strlen(v);
	if (len + vlen < KAZ_MAX_STEM_BYTES)
	{
		memcpy(trial, lexeme, len);
		memcpy(trial + len, v, vlen);
		trial[len + vlen] = '\0';
		if (kaz_lexicon_contains(lexicon, trial, len + vlen))
		{
			pfree(lexeme);
			return pstrdup(trial);
		}
	}

	v = is_back ? "а" : "е";
	vlen = (int) strlen(v);
	if (len + vlen < KAZ_MAX_STEM_BYTES)
	{
		memcpy(trial, lexeme, len);
		memcpy(trial + len, v, vlen);
		trial[len + vlen] = '\0';
		if (kaz_lexicon_contains(lexicon, trial, len + vlen))
		{
			pfree(lexeme);
			return pstrdup(trial);
		}
	}

	return lexeme;
}

static void
kaz_init_default_weights(KazPenaltyWeights *w)
{
	w->w_no_strip = KAZ_DEFAULT_W_NO_STRIP;
	w->w_short_char = KAZ_DEFAULT_W_SHORT_CHAR;
	w->w_no_syll = KAZ_DEFAULT_W_NO_SYLL;
	w->w_two_char = KAZ_DEFAULT_W_TWO_CHAR;
	w->w_three_one = KAZ_DEFAULT_W_THREE_ONE;
	w->w_deriv = KAZ_DEFAULT_W_DERIV;
	w->w_weak = KAZ_DEFAULT_W_WEAK;
	w->w_single_char = KAZ_DEFAULT_W_SINGLE_CHAR;
	w->w_verb_all_weak = KAZ_DEFAULT_W_VERB_ALL_WEAK;
	w->w_nik_deriv = KAZ_DEFAULT_W_NIK_DERIV;
	w->w_final_cons = KAZ_DEFAULT_W_FINAL_CONS;
	w->w_nominal_inf = KAZ_DEFAULT_W_NOMINAL_INF;
	w->w_verbal_inf = KAZ_DEFAULT_W_VERBAL_INF;
	w->w_removed = KAZ_DEFAULT_W_REMOVED;
	w->w_verb_track = KAZ_DEFAULT_W_VERB_TRACK;
}

static bool
kaz_try_parse_weight(const char *name, const char *value, KazPenaltyWeights *w)
{
	struct
	{
		const char *key;
		double	   *dst;
	}			map[] = {
		{"w_no_strip", &w->w_no_strip},
		{"w_short_char", &w->w_short_char},
		{"w_no_syll", &w->w_no_syll},
		{"w_two_char", &w->w_two_char},
		{"w_three_one", &w->w_three_one},
		{"w_deriv", &w->w_deriv},
		{"w_weak", &w->w_weak},
		{"w_single_char", &w->w_single_char},
		{"w_verb_all_weak", &w->w_verb_all_weak},
		{"w_nik_deriv", &w->w_nik_deriv},
		{"w_final_cons", &w->w_final_cons},
		{"w_nominal_inf", &w->w_nominal_inf},
		{"w_verbal_inf", &w->w_verbal_inf},
		{"w_removed", &w->w_removed},
		{"w_verb_track", &w->w_verb_track},
	};
	int			i;

	for (i = 0; i < (int) lengthof(map); i++)
	{
		if (strcmp(name, map[i].key) == 0)
		{
			char	   *endp;
			double		v = strtod(value, &endp);

			if (endp == value || *endp != '\0')
				ereport(ERROR,
						(errcode(ERRCODE_INVALID_PARAMETER_VALUE),
						 errmsg("invalid value for pg_kazsearch weight \"%s\": \"%s\"",
								name, value)));
			*map[i].dst = v;
			return true;
		}
	}
	return false;
}

Datum
pg_kazsearch_init(PG_FUNCTION_ARGS)
{
	List *dictoptions = (List *) PG_GETARG_POINTER(0);
	KazStemCfg *cfg = palloc0_object(KazStemCfg);
	ListCell *l;
	char *lexicon_name = NULL;

	cfg->derivation = true;
	cfg->max_steps = 8;
	kaz_init_default_weights(&cfg->weights);

	foreach(l, dictoptions)
	{
		DefElem *defel = (DefElem *) lfirst(l);

		if (strcmp(defel->defname, "derivation") == 0)
			cfg->derivation = defGetBoolean(defel);
		else if (strcmp(defel->defname, "max_steps") == 0)
			cfg->max_steps = pg_strtoint32(defGetString(defel));
		else if (strcmp(defel->defname, "lexicon") == 0)
			lexicon_name = defGetString(defel);
		else if (!kaz_try_parse_weight(defel->defname, defGetString(defel), &cfg->weights))
			ereport(ERROR,
					(errcode(ERRCODE_INVALID_PARAMETER_VALUE),
					 errmsg("unrecognized pg_kazsearch parameter: \"%s\"", defel->defname)));
	}

	if (cfg->max_steps < 1)
		cfg->max_steps = 1;
	if (cfg->max_steps > 16)
		cfg->max_steps = 16;
	if (lexicon_name != NULL && *lexicon_name != '\0')
		cfg->lexicon = kaz_load_lexicon_table(lexicon_name);

	PG_RETURN_POINTER(cfg);
}

Datum
pg_kazsearch_lexize(PG_FUNCTION_ARGS)
{
	KazStemCfg *cfg = (KazStemCfg *) PG_GETARG_POINTER(0);
	char *in = (char *) PG_GETARG_POINTER(1);
	int32 len = PG_GETARG_INT32(2);
	char *txt;
	int *chars_prefix = NULL;
	int *syll_prefix = NULL;
	KazExploreResult noun;
	KazExploreResult verb;
	KazCandidate *best;
	int original_chars;
	char *lexeme;
	TSLexeme *res;

	if (len <= 0)
		PG_RETURN_POINTER(NULL);

	txt = str_tolower(in, len, DEFAULT_COLLATION_OID);
	if (*txt == '\0')
		PG_RETURN_POINTER(NULL);

	len = (int32) strlen(txt);

	if (kaz_is_exception(txt, len))
	{
		res = palloc0_array(TSLexeme, 2);
		res[0].lexeme = txt;
		PG_RETURN_POINTER(res);
	}

	chars_prefix = palloc(sizeof(int) * (len + 1));
	syll_prefix = palloc(sizeof(int) * (len + 1));
	kaz_fill_prefix_tables(txt, len, chars_prefix, syll_prefix);

	if (syll_prefix[len] < 2)
	{
		pfree(chars_prefix);
		pfree(syll_prefix);
		res = palloc0_array(TSLexeme, 2);
		res[0].lexeme = txt;
		PG_RETURN_POINTER(res);
	}

	original_chars = chars_prefix[len];
	noun = kaz_explore_track_best(txt, len, kaz_noun_layers, kaz_noun_layer_count, cfg, true,
								  chars_prefix, syll_prefix);
	verb = kaz_explore_track_best(txt, len, kaz_verb_layers, kaz_verb_layer_count, cfg, false,
								  chars_prefix, syll_prefix);

	best = NULL;
	if (cfg->lexicon != NULL && (noun.has_lexhit || verb.has_lexhit))
	{
		KazCandidate *best_lex = NULL;
		bool shallow_ambiguous = false;

		if (noun.has_lexhit && verb.has_lexhit)
		{
			double np = kaz_candidate_penalty(&noun.best_lexhit, txt, original_chars, false,
											  chars_prefix, syll_prefix, &cfg->weights);
			double vp = kaz_candidate_penalty(&verb.best_lexhit, txt, original_chars, true,
											  chars_prefix, syll_prefix, &cfg->weights);

			if (kaz_candidate_beats(&verb.best_lexhit, &noun.best_lexhit, vp, np, txt, chars_prefix))
				best_lex = &verb.best_lexhit;
			else
				best_lex = &noun.best_lexhit;
		}
		else if (noun.has_lexhit)
			best_lex = &noun.best_lexhit;
		else
			best_lex = &verb.best_lexhit;

		if (best_lex != NULL)
		{
			bool lex_input_is_known = kaz_lexicon_contains(cfg->lexicon, txt, len);

			shallow_ambiguous = best_lex->steps == 1 && syll_prefix[len] <= 2;
			if (lex_input_is_known &&
				(shallow_ambiguous ||
				 (syll_prefix[len] >= 3 &&
				  syll_prefix[best_lex->len] < syll_prefix[len])))
			{
				pfree(chars_prefix);
				pfree(syll_prefix);
				res = palloc0_array(TSLexeme, 2);
				res[0].lexeme = txt;
				PG_RETURN_POINTER(res);
			}
			else
				best = best_lex;
		}
	}

	if (best == NULL)
	{
		double np = kaz_candidate_penalty(&noun.best_scored, txt, original_chars, false,
										  chars_prefix, syll_prefix, &cfg->weights);
		double vp = kaz_candidate_penalty(&verb.best_scored, txt, original_chars, true,
										  chars_prefix, syll_prefix, &cfg->weights);
		bool input_is_known = cfg->lexicon != NULL &&
			kaz_lexicon_contains(cfg->lexicon, txt, len);

		if (kaz_candidate_beats(&verb.best_scored, &noun.best_scored, vp, np, txt, chars_prefix))
			best = &verb.best_scored;
		else
			best = &noun.best_scored;

		if (input_is_known &&
			(!kaz_candidate_hits_lexicon(best, txt, cfg->lexicon) ||
			 (best->steps > 0 && best->single_char == best->steps) ||
			 syll_prefix[best->len] < syll_prefix[len]))
		{
			pfree(chars_prefix);
			pfree(syll_prefix);
			res = palloc0_array(TSLexeme, 2);
			res[0].lexeme = txt;
			PG_RETURN_POINTER(res);
		}
	}

	lexeme = pnstrdup(txt, best->len);

	if (best->steps > 0 && best->nominal_inf > 0 && best->last_suffix &&
		kaz_suffix_in(best->last_suffix, kaz_poss_vowel_suffixes, kaz_poss_vowel_suffix_count))
	{
		int lexeme_len = (int) strlen(lexeme);

		kaz_apply_mutation(lexeme, lexeme_len);
		lexeme = kaz_apply_elision_restore(lexeme, (int) strlen(lexeme));
	}
	lexeme = kaz_restore_lexicon_vowel(lexeme, cfg->lexicon, best->steps);

	res = palloc0_array(TSLexeme, 2);
	res[0].lexeme = lexeme;

	pfree(chars_prefix);
	pfree(syll_prefix);
	pfree(txt);
	PG_RETURN_POINTER(res);
}
