/*
 * Lexicon hash table load and membership tests.
 */
#include "postgres.h"

#include "storage/fd.h"
#include "tsearch/ts_public.h"

#include "kaz_internal.h"

bool
kaz_lexicon_contains(HTAB *lexicon, const char *word, int len)
{
	char key[KAZ_MAX_STEM_BYTES];
	bool found;

	if (lexicon == NULL || len <= 0 || len >= KAZ_MAX_STEM_BYTES)
		return false;

	memcpy(key, word, len);
	key[len] = '\0';
	hash_search(lexicon, key, HASH_FIND, &found);
	return found;
}

HTAB *
kaz_load_lexicon_table(const char *lexicon_name)
{
	HASHCTL ctl;
	HTAB *lexicon;
	char *path;
	FILE *fp;
	char line[512];

	MemSet(&ctl, 0, sizeof(ctl));
	ctl.keysize = KAZ_MAX_STEM_BYTES;
	ctl.entrysize = sizeof(KazLexiconEntry);
	lexicon = hash_create("pg_kazsearch lexicon",
						  65536,
						  &ctl,
						  HASH_ELEM | HASH_STRINGS);

	path = get_tsearch_config_filename(lexicon_name, "dict");
	fp = AllocateFile(path, "r");
	if (fp == NULL)
		ereport(ERROR,
				(errcode_for_file_access(),
				 errmsg("could not open pg_kazsearch lexicon file \"%s\": %m", path)));

	while (fgets(line, sizeof(line), fp) != NULL)
	{
		char *start = line;
		char *end;
		bool found;

		while (*start == ' ' || *start == '\t' || *start == '\r' || *start == '\n')
			start++;
		if (*start == '\0' || *start == '#')
			continue;

		end = start + strlen(start);
		while (end > start && (end[-1] == ' ' || end[-1] == '\t' || end[-1] == '\r' || end[-1] == '\n'))
			end--;
		*end = '\0';

		if ((int) strlen(start) >= KAZ_MAX_STEM_BYTES)
			ereport(ERROR,
					(errcode(ERRCODE_INVALID_PARAMETER_VALUE),
					 errmsg("pg_kazsearch lexicon entry is too long: \"%s\"", start)));

		hash_search(lexicon, start, HASH_ENTER, &found);
	}

	if (FreeFile(fp) != 0)
		ereport(ERROR,
				(errcode_for_file_access(),
				 errmsg("could not close pg_kazsearch lexicon file \"%s\": %m", path)));
	pfree(path);

	return lexicon;
}
