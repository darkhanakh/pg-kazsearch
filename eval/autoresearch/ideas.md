# Deferred ideas (autoresearch sbl-kazqad)

- Possessive -ы/-і not after vowel+қ/к (екі, ақын, жалақы keep root). Clean: train 4/2, val 4/0, lo99 -0.00016 (#10). Bundle with another voicing guard.
- Genitive/ablative -ның/-нан after м (адамның->адам) (#3): correct, +0.0007, 41/47. Too noisy alone.
- -ған/-ген on one-syllable consonant-final base with voicing agreement (#2): +0.0025, lo99 -0.00025. Loss: қорған(ы)->қор (Great Wall).
- Present -ады on one-syllable V+C base (#5): +0.0011; loss жасады->жас.
- two_syllables counting C+у/и+C as nucleus (#7): neutral; французша hurts.
- Instrumental -мен/-бен/-пен allomorphs (#9): loanwords break it (Буллзмен).
- -сы guard: treat у before ы/і as consonant (дауысы->дауыс, қуысы->қуыс).
- 2pl formal present -йсыз/-асыз (атайсыз, табасыз in questions): collides with privative on -ай/-а nouns (қолайсыз, қамтамасыз). Not run.
- CV bases with у/и (су, ми): мидағы->мидақ, судың unstemmed. Allowing hurts жиі, буын, Судан. Not run.
- Surnames: front root + -ов takes front suffixes (Әуезовтің) - mirror of the -ев rule. Small.
- Habitual -атын on 2-syl base (#17): +0.0006 noisy. Verb conflation is a wash on KazQAD (#2,#5,#6,#11,#17).
- Past -ты/-ті refused after -лық/-дық/-тық (so тәуелсіздікті joins тәуелсіздік): also sends adjectives жергілікті->жер, күнделікті->күн. Not run.
- Family splits found by /tmp/kz/split.py: -ның/-нан after м (biggest), белгісі/белгі (-сы guard after г), алғашқысы/соңғысы (-сы after қы/ғы).
- Drop 1pl past -дық/-тық from tense table (verb chain cuts аштық->аш while аштықтан stays аштық). Side effect: бостандық -> бос via derivation + -тан ablative cascade (37 queries). Not run.
## Near-pass candidates (positive mean, lo99 < 0)
- #29 verbal noun -у after consonant on 2-syl base (+0.0015 train, +0.0011 val, +0.0044 news; 37/56). /tmp/kz/exp29.sbl
- #30 base_ok accepts C+у/и (су, ми, ту families) (+0.0012, 20/11; Судан->су -1.0). /tmp/kz/exp30.sbl
- #27 -ушы -> verbal noun (+0.0008, 24/18). #18 м-genitive (+0.0008, 44/49).
- -ады guard: reject consonant+д (тасымалдады->тасымалд bug; қабылдады->қабыл). 7 train queries. Not run. patch in /tmp/kz/patches/ady_d.*
- Vowel-stem verbal nouns (жасау): NO - атау, жағалау, Мәскеу, -тау place names are lexicalized.
## After keep #38 (non-finite verbs)
- Kept bundle: verbal noun after consonant + habitual -атын 2-syl + voiceless -қан 1-syl + -ады d-fix.
- Remaining verb gaps: voiced -ған on 1-syl (қорған risk), present -ады on 1-syl (жасады->жас risk), converb -ып 1-syl (кәсіп), -п after vowel stems (кітап risk).
- BUG in kept #38 (habitual guard): locative_adjective leaves "-ын" and the habitual guard then blocks possessive_n: сайтындағы->сайтын, мемлекетіндегі->мемлек. Fix: locative_adjective does `try ( possessive_n try possessive )` like case. /tmp/kz/exp42.sbl. Zero query footprint (784 df) -> cannot pass gate alone; fold into a later keep if possible.
