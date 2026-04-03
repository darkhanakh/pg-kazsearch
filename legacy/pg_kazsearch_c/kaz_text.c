/*
 * UTF-8 iteration, vowel harmony, and byte-level suffix checks.
 */
#include "postgres.h"

#include "kaz_internal.h"

bool
kaz_utf8_next_cp(const char *s, int len, int *idx, uint32 *cp)
{
	unsigned char c;
	int i = *idx;

	if (i >= len)
		return false;

	c = (unsigned char) s[i];
	if (c < 0x80)
	{
		*cp = c;
		*idx = i + 1;
		return true;
	}
	if ((c & 0xE0) == 0xC0 && i + 1 < len)
	{
		*cp = ((uint32) (c & 0x1F) << 6) | (uint32) (((unsigned char) s[i + 1]) & 0x3F);
		*idx = i + 2;
		return true;
	}
	if ((c & 0xF0) == 0xE0 && i + 2 < len)
	{
		*cp = ((uint32) (c & 0x0F) << 12) |
			((uint32) (((unsigned char) s[i + 1]) & 0x3F) << 6) |
			(uint32) (((unsigned char) s[i + 2]) & 0x3F);
		*idx = i + 3;
		return true;
	}
	if ((c & 0xF8) == 0xF0 && i + 3 < len)
	{
		*cp = ((uint32) (c & 0x07) << 18) |
			((uint32) (((unsigned char) s[i + 1]) & 0x3F) << 12) |
			((uint32) (((unsigned char) s[i + 2]) & 0x3F) << 6) |
			(uint32) (((unsigned char) s[i + 3]) & 0x3F);
		*idx = i + 4;
		return true;
	}

	*cp = c;
	*idx = i + 1;
	return true;
}

bool
kaz_utf8_last_cp(const char *s, int len, uint32 *cp)
{
	int i = 0;
	bool found = false;
	uint32 c = 0;

	while (i < len)
	{
		if (!kaz_utf8_next_cp(s, len, &i, &c))
			break;
		found = true;
	}
	if (found)
		*cp = c;
	return found;
}

int
kaz_utf8_char_count(const char *s, int len)
{
	int i = 0;
	int n = 0;
	uint32 cp;

	while (i < len && kaz_utf8_next_cp(s, len, &i, &cp))
		n++;
	return n;
}

static bool
kaz_is_loan_vowel(uint32 cp)
{
	/* я (U+044F), э (U+044D) — loanword graphemes that form syllables */
	return cp == 0x044F || cp == 0x044D;
}

/*
 * One UTF-8 pass: chars_prefix[b] / syll_prefix[b] = counts in word[0..b).
 * Valid for every byte offset b that is a UTF-8 boundary; interior bytes of
 * a multibyte character inherit the counts at the end of that character.
 */
void
kaz_fill_prefix_tables(const char *word, int len, int *chars_prefix, int *syll_prefix)
{
	int i = 0;
	int nchars = 0;
	int nsyll = 0;

	chars_prefix[0] = 0;
	syll_prefix[0] = 0;
	while (i < len)
	{
		int start = i;
		uint32 cp;

		if (!kaz_utf8_next_cp(word, len, &i, &cp))
		{
			int b;

			for (b = start + 1; b <= len; b++)
			{
				chars_prefix[b] = nchars;
				syll_prefix[b] = nsyll;
			}
			return;
		}
		nchars++;
		if (kaz_is_vowel(cp) || kaz_is_loan_vowel(cp))
			nsyll++;
		{
			int b;

			for (b = start + 1; b <= i; b++)
			{
				chars_prefix[b] = nchars;
				syll_prefix[b] = nsyll;
			}
		}
	}
	{
		int b;

		for (b = i + 1; b <= len; b++)
		{
			chars_prefix[b] = nchars;
			syll_prefix[b] = nsyll;
		}
	}
}

bool
kaz_is_back_vowel(uint32 cp)
{
	return cp == 0x0430 || cp == 0x043E || cp == 0x04B1 || cp == 0x044B || cp == 0x0443;
}

bool
kaz_is_front_vowel(uint32 cp)
{
	return cp == 0x04D9 || cp == 0x0435 || cp == 0x04E9 || cp == 0x04AF || cp == 0x0456 || cp == 0x0438 || cp == 0x0451;
}

bool
kaz_is_vowel(uint32 cp)
{
	return kaz_is_back_vowel(cp) || kaz_is_front_vowel(cp);
}

int
kaz_count_syllables(const char *s, int len)
{
	int i = 0;
	int n = 0;
	uint32 cp;

	while (i < len && kaz_utf8_next_cp(s, len, &i, &cp))
	{
		if (kaz_is_vowel(cp) || kaz_is_loan_vowel(cp))
			n++;
	}
	return n;
}

bool
kaz_is_glide(uint32 cp)
{
	/* у (U+0443), и (U+0438), ю (U+044E) */
	return cp == 0x0443 || cp == 0x0438 || cp == 0x044E;
}

bool
kaz_word_is_back(const char *s, int len)
{
	int i = 0;
	uint32 cp;
	bool found = false;
	bool back = true;

	while (i < len && kaz_utf8_next_cp(s, len, &i, &cp))
	{
		if (kaz_is_glide(cp))
			continue;
		if (kaz_is_back_vowel(cp))
		{
			found = true;
			back = true;
		}
		else if (kaz_is_front_vowel(cp))
		{
			found = true;
			back = false;
		}
	}
	return found ? back : true;
}

static bool
kaz_tail_is_back(const char *s, int len)
{
	int i = 0;
	uint32 cp;
	uint32 last_two[2] = {0, 0};
	int n = 0;

	while (i < len && kaz_utf8_next_cp(s, len, &i, &cp))
	{
		if (kaz_is_glide(cp))
			continue;
		if (kaz_is_back_vowel(cp) || kaz_is_front_vowel(cp) || kaz_is_loan_vowel(cp))
		{
			last_two[0] = last_two[1];
			last_two[1] = cp;
			n++;
		}
	}
	if (n == 0)
		return true;
	if (kaz_is_loan_vowel(last_two[1]))
		return last_two[0] != 0 ? kaz_is_back_vowel(last_two[0]) : true;
	return kaz_is_back_vowel(last_two[1]);
}

bool
kaz_harmony_ok(const char *s, int len, uint8 harmony)
{
	bool full_back;

	if (harmony == KAZ_HARM_ANY)
		return true;
	if (len <= 0)
		return false;

	full_back = kaz_word_is_back(s, len);
	if (harmony == KAZ_HARM_BACK && full_back)
		return true;
	if (harmony == KAZ_HARM_FRONT && !full_back)
		return true;

	if (kaz_count_syllables(s, len) >= 4)
	{
		bool tail_back = kaz_tail_is_back(s, len);
		if (harmony == KAZ_HARM_BACK)
			return tail_back;
		return !tail_back;
	}

	return false;
}

bool
kaz_ends_with_bytes_n(const char *s, int len, const char *suffix, int suffix_len, int *base_len)
{
	if (suffix_len <= 0 || suffix_len >= len)
		return false;
	if (memcmp(s + len - suffix_len, suffix, suffix_len) != 0)
		return false;
	if (base_len)
		*base_len = len - suffix_len;
	return true;
}

bool
kaz_ends_with_bytes(const char *s, int len, const char *suffix, int *base_len)
{
	return kaz_ends_with_bytes_n(s, len, suffix, (int) strlen(suffix), base_len);
}

bool
kaz_ends_with_any_n(const char *s, int len, const char *const *suffixes, const int *suffix_lens,
					int n)
{
	int i;
	for (i = 0; i < n; i++)
	{
		if (kaz_ends_with_bytes_n(s, len, suffixes[i], suffix_lens[i], NULL))
			return true;
	}
	return false;
}

bool
kaz_ends_with_any(const char *s, int len, const char *const *suffixes, int n)
{
	int i;
	for (i = 0; i < n; i++)
	{
		if (kaz_ends_with_bytes_n(s, len, suffixes[i], (int) strlen(suffixes[i]), NULL))
			return true;
	}
	return false;
}

bool
kaz_suffix_in(const char *sfx, const char *const *arr, int n)
{
	int i;
	for (i = 0; i < n; i++)
	{
		if (strcmp(sfx, arr[i]) == 0)
			return true;
	}
	return false;
}
