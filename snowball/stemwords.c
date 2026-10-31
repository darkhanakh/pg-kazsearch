/* Minimal line-oriented driver for the generated Kazakh stemmer.
 * Reads one UTF-8 word per line on stdin, writes "word<TAB>stem" per line.
 * Built by eval_snowball.py against the Snowball C runtime. */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "snowball_runtime.h"
#include "kazakh.h"

int main(void) {
    struct SN_env *z = kazakh_UTF_8_create_env();
    char line[1024];
    if (!z) return 1;
    while (fgets(line, sizeof line, stdin)) {
        size_t n = strlen(line);
        while (n && (line[n - 1] == '\n' || line[n - 1] == '\r')) line[--n] = 0;
        if (SN_set_current(z, (int)n, (const symbol *)line)) return 2;
        if (kazakh_UTF_8_stem(z) < 0) return 3;
        z->p[z->l] = 0;
        printf("%s\t%s\n", line, (const char *)z->p);
    }
    kazakh_UTF_8_close_env(z);
    return 0;
}
