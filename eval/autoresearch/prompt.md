# Autoresearch: Kazakh Snowball stemmer on KazQAD train

## Objective
Improve BM25 retrieval with the Snowball Kazakh stemmer `snowball/kazakh.sbl`, measured as nDCG@10 on the
KazQAD train split (3,487 exam questions against 825,309 Kazakh Wikipedia passages, BM25 k1=0.9 b=0.4).
This stemmer is under review upstream (snowballstem/snowball#313). Anything kept here may become a
follow-up PR, so every kept rule must be one a Kazakh grammar can justify, not a number-fitting trick.

## Metrics
- **Primary**: `ndcg_train` (unitless, higher is better).
- **Secondary**: `d_train` and `lo99_train` (gain over the last kept version and the 99% paired-bootstrap
  lower bound of that gain), `d_val` (gain on KazQAD validation, 548 questions), `d_news_r10` (recall@10
  change on a 132-query Kazakh news set), `train_wins` / `train_losses` (questions that got better or
  worse), `gate_pass`, `eval_seconds`.

## How to Run
`./.auto/measure.sh` compares the working `snowball/kazakh.sbl` with the one at `HEAD` (the last kept
version) and prints `METRIC` lines. One run takes a few minutes; the baseline's scores are cached.

## The gate
`./.auto/checks.sh` blocks a keep unless all of these hold:
- the file compiles with the pinned Snowball compiler with no warnings,
- the train gain's 99% lower bound is above zero,
- the validation gain is positive,
- news recall@10 is not significantly worse and drops by no more than 0.015,
- only `snowball/kazakh.sbl` changed, and the scoring harness is untouched.

The pi confidence score does not apply here. The benchmark is deterministic, so run-to-run spread is
zero; the real noise is which questions are in the set, and only the gate measures that. Do not re-run
to "confirm" a result: the same input gives the same output. A higher `ndcg_train` that fails the gate
is noise and must be discarded. Equal-metric simplifications also fail the gate; that is intended.

## Files in Scope
- `snowball/kazakh.sbl`: the stemmer. Rules, groupings, among tables, routines and comments.

## Off Limits
- Everything else in this repository, and everything under `~/exp/kazsbl/harness`.
- KazQAD test. It is the held-out check for the end of the session. Never read the test topics or
  qrels and never run `eval/run_kazqad.py`.

## Constraints
- Each kept change must come with a comment in `kazakh.sbl` stating the grammatical reason and at least
  one example word with its stem. If you cannot write that comment honestly, discard the change.
- Prefer changes that a native speaker would recognise: a missing allomorph, a harmony case, a suffix
  slot, a guard against a known class of roots. Avoid length thresholds or word lists tuned to the data.
- Keep the file portable Snowball: no new external dependencies, nothing that only one backend accepts.
- Stop after the configured iteration cap.

## Where to look first
- The header comment of `kazakh.sbl` lists suffixes deliberately left alone and the evidence behind
  each. Several rest on judgment, not measurement: first and second person endings, the privative, the
  similative, `-ған/-ып` on one-syllable bases, the reflexive `-ын/-ін`. These are fair game for a test.
- Known ambiguities are listed there too (`-ны` after a vowel, `-сы` after consonant + ы/і, `-ғы` after
  a consonant, final `-ы/-і`). A better-guarded reading of one of these is a good candidate.
- The verbal noun `-у` and voice suffixes were tested before on the news set and tied within noise;
  KazQAD train is larger, so a retest is legitimate.

## What's Been Tried
Session sbl-kazqad-2026-11-02, 60 runs (cap). Train nDCG@10 0.33503 -> 0.34321 (+0.0082) over five
kept versions. Run numbers refer to `.auto/log.jsonl`. KazQAD test was never read or run.

### Kept (each passed the gate against the version before it)
- #8 Temporal adjective `-ғы/-гі` only after a voiced consonant, `-қы/-кі` only after a voiceless one.
  халқы -> халық, түркі -> түрк, жылқы no longer -> жыл. Train +0.0008 (13 wins / 1 loss), val +0.0014.
- #13 Harmony: у/и/ю after a consonant spell a vowel of unknown class, so a base whose last vowel is
  one of them takes either class (Париж-де, Мадрид-те, организм-дер, ресурс-тар). Also no accusative
  `-ны` and no possessive `-сы` after и (термин-і, артис-і). Train +0.0028, val +0.0045. Biggest
  clean win: KazQAD questions are full of foreign names and terms with Kazakh case endings.
- #23 Final `-ы/-і` and `-сы` read by the consonant before them: no bare possessive after vowel + қ/к
  (екі, ақын, жалақы keep the vowel, since the possessive would have voiced қ/к); `-сы` never after у
  and the glide у counts as a consonant (вирус-ы, дауыс-ы, туыс-ы); `-сы` allowed after г/к/қ + ы/і
  (белгі-сі, алғашқы-сы); the `-ғы` adjective is tried before the possessive under a case suffix
  (жылғыдан -> жыл). Train +0.0009 (lo99 +0.00002, the narrowest pass), val +0.0012, news +0.0011.
- #38 Non-finite verb forms reach the verb stem: verbal noun `-у` after a consonant on a two-syllable
  base (басқару -> басқар), habitual `-атын/-етін` on a two-syllable base (табылатын -> табыл; loans
  with о/ө after the first syllable excluded, чемпионат), voiceless `-қан/-кен` on a one-syllable base
  (шыққан -> шық); `-ады` refused after consonant + д (тасымалдады -> тасымал, not тасымалд). Train
  +0.0038 (87 wins / 127 losses), val +0.0005, news +0.003. Ablations #47-#49: verbal noun +0.0021
  train / +0.0026 news / -0.0003 val; habitual +0.0006 train / +0.0004 val; one-syllable `-қан`
  +0.0017 train but -0.0010 val and -0.0014 news. The `-қан` part's train gain does not transfer;
  review it before upstreaming.
- Known side effect of #38 (no retrieval effect, never kept): the habitual guard makes
  locative-adjective forms keep `-ын` (сайтындағы -> сайтын, мемлекетіндегі -> мемлек). The fix is
  `try ( possessive_n try possessive )` at the end of `locative_adjective` (#43, #56).

### Tried and failed the gate (main reason)
- Verb conflation for one-syllable verbs is a wash or worse: voiced `-ған` (#2, #39 even after #38),
  present `-ады` (#5, #42), both (#6), voiceless `-қан` alone before #38 (#11). Losses: қорған(ы)
  -> қор (Great Wall questions), өткен/өтеді merging with өт 'bile', жасады -> жас.
- Voice: passive `-ыл/-іл` (#41, +0.0003) and causative `-ғыз/-қыз` (#43) are neutral, as on news.
- Habitual `-атын` alone (#17) and verbal noun alone (#29, #31) were positive but noisy; they passed
  only together (#38). C+у/и bases (су-дың, ми-да, ту-ы; #30) +0.0012 but Судан -> су and су idf
  losses; bundled with the verbal noun it missed by lo99 -0.00008 (#32, #34) and with the м-genitive
  by -0.0008 (#40).
- Genitive/ablative `-ның/-нан` after м (адамның -> адам) is correct but noisy: +0.0007/+0.0008
  (#3, #18). Merging into high-idf кім and frequent фильм/әлем/адам moves many queries both ways.
- Accusative `-ны` after a vowel vs н-stem + possessive (өзені, ауданы -> өзе, ауда): dropping the
  accusative (#4) is a wash, because questions use the accusative of vowel-final names (Алясканы,
  Энергияны, Фортепианоны кім ойлап тапты); variants after и (#12) and о (#16) also fail.
- Harmony refinements beyond #13: soft sign takes either class (#14, #19), и after a vowel and front
  `-ов` surnames (#44, val +0.0035 but train untouched). Good upstream candidates, invisible to the
  train gate.
- Allomorph guards with tiny footprints: instrumental `-мен/-бен/-пен` (#9; loans write Буллзмен),
  plural conditions inside `-лары/-дары` (#15), participle and `-лық` voicing (#59, val +0.0009, train
  0/0), deverbal `-ғын` keeps its н (#51, zero effect), `-ыш` nouns + possessive (#37, кіші -> кіш).
- Syllable counting: и between consonants as a nucleus (#7 with у, #26 и only): физикалық -> физика
  lowers idf for physics questions; neutral.
- Derivation changes: no `-ша/-ше` (#35; diminutives like түтікше were useful), no ordinal `-ншы`
  (#45), `-дық/-тық` on one-syllable bases (#25), dropping the 1pl past `-дық/-тық` (#24, -0.0015;
  кванттық/микробтық merges help), vowel + ш possessive (#36), agent `-ушы` -> verbal noun (#27),
  terminal agent slot (#28, #50, #56: clean, 4/2, lo99 -0.00005).
- Other: postlude г after о -> к (кубогы -> кубок, #33, zero effect), `-ді` after consonant + д,
  `-са`/`-май` removal (#53), formal `-йсыз` (#46, zero effect), `-ты` after `-лық` (not run:
  жергілікті -> жер).

### Design ablations (rules already in the file; none should be removed)
- Nominal repeat loop -> one ordered pass (#54): -0.0033 train, -0.0008 val, -0.0043 news. The
  consistency-over-correctness trade in the header is supported.
- Nominal `-лық/-дық/-тық` derivation off (#52): -0.0032 train, -0.0053 val (news +0.0073).
- Converb `-ып` on two syllables off (#58): -0.0017 / -0.0015 / -0.0051. Participle `-ған` off
  (#60): -0.0085 train, val +0.0009. Verbalizer off (#55) and negation off (#57): neutral.

### Lessons
- Clean wins come from removing collisions or unblocking foreign names (#8, #13). Changes that merge
  frequent forms (verb forms, frequent nouns) move hundreds of queries both ways, and only large or
  bundled effects clear lo99 > 0.
- A recall proxy (query terms newly matching relevant train passages) did not predict the gate; idf
  shifts on frequent query stems dominate.
- The question words кім, қашан, қайда, қандай have df 400-3,000 in the passages and so a high idf.
  They are the main reason zero-score questions fail, but they are outside the stemmer's remit.
- Remaining ambiguities need a lexicon: `-ны` after a vowel, roots in `-ын/-ін` (ойын -> ой, алтын ->
  алт, орын -> ор), `-сы` after а/е (кеңесі -> кеңе), and homographs (тағы/тақ, ұлы/ұл, жазды/жаз).
