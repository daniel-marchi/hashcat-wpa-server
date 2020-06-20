import datetime
import re
from collections import namedtuple
from functools import lru_cache

from app import lock_app
from app.attack.hashcat_cmd import HashcatCmdStdout
from app.domain import WordList, Rule
from app.logger import logger
from app.utils import subprocess_call
from app.utils.file_io import calculate_md5
from app.utils.file_io import read_last_benchmark
from app.word_magic.digits.create_digits import read_mask

WordListInfo = namedtuple('WordListInfo', ('rate', 'count', 'url', 'checksum'))


WORDLISTS_DOWNLOADABLE = {
    WordList.TOP109M: WordListInfo(
        rate=39,
        count=109438614,
        url="https://download.weakpass.com/wordlists/1852/Top109Million-probable-v2.txt.gz",
        checksum="c0a26fd763d56a753a5f62c517796d09"
    ),
    WordList.TOP29M: WordListInfo(
        rate=30,
        count=29040646,
        url="https://download.weakpass.com/wordlists/1857/Top29Million-probable-v2.txt.gz",
        checksum="4d86278a7946fe9ad7016440e85ff2b6"
    ),
    WordList.TOP1M: WordListInfo(
        rate=19,
        count=1667462,
        url="https://download.weakpass.com/wordlists/1855/Top1pt6Million-probable-v2.txt.gz",
        checksum="2d45c4aa9f4a87ece9ebcbd542613f50"
    ),
    WordList.TOP304K: WordListInfo(
        rate=12,
        count=303872,
        url="https://download.weakpass.com/wordlists/1859/Top304Thousand-probable-v2.txt.gz",
        checksum="f99e6a581597cbdc76efc1bcc001a9ed"
    ),
}


def get_wordlist_rate(wordlist: WordList):
    if wordlist not in WORDLISTS_DOWNLOADABLE:
        return None
    return WORDLISTS_DOWNLOADABLE[wordlist].rate


def download_wordlist(wordlist: WordList):
    if wordlist is None:
        return
    if wordlist.path.exists():
        return
    if wordlist not in WORDLISTS_DOWNLOADABLE:
        return
    rate, count, url, checksum = WORDLISTS_DOWNLOADABLE[wordlist]
    gzip_file = url.split('/')[-1]
    gzip_file = wordlist.path.with_name(gzip_file)
    logger.debug(f"Downloading {gzip_file}")
    while calculate_md5(gzip_file) != checksum:
        subprocess_call(['wget', url, '-O', gzip_file])
    with lock_app:
        subprocess_call(['gzip', '-d', gzip_file])
    logger.debug(f"Downloaded and extracted {wordlist.path}")



@lru_cache(maxsize=16)
def count_words(wordlist: WordList):
    if wordlist is None:
        return 0
    if wordlist in WORDLISTS_DOWNLOADABLE:
        return WORDLISTS_DOWNLOADABLE[wordlist].count
    out, err = subprocess_call(['wc', '-l', str(wordlist.path)])
    out = out.rstrip('\n')
    counter = 0
    if re.fullmatch(f"\d+ {wordlist.path}", out):
        counter, path = out.split(' ')
    counter = int(counter)
    return counter


@lru_cache(maxsize=4)
def count_rules(rule: Rule):
    # counts the multiplier
    if rule is None:
        return 1
    rules = read_mask(rule.path)
    return len(rules)


def estimate_runtime_fmt(wordlist: WordList, rule: Rule) -> str:
    speed = int(read_last_benchmark().speed)
    if speed == 0:
        return "unknown"
    # add extra words to account for the 'fast' run, which includes
    # 160k digits8, 120k top1k+best64 and ESSID manipulation
    # (300k hamming ball, 70k digits append mask)
    n_words = count_words(wordlist) + 700_000
    n_candidates = n_words * count_rules(rule)
    runtime = int(n_candidates / speed)  # in seconds
    runtime_ftm = str(datetime.timedelta(seconds=runtime))
    return runtime_ftm


def create_fast_wordlists():
    # note that dumping all combinations in a file is not equivalent to
    # directly adding top1k wordlist and best64 rule because hashcat ignores
    # patterns that are <8 chars _before_ expanding a candidate with the rule.
    if not WordList.TOP1K_RULE_BEST64.path.exists():
        # it should be already created in a docker
        logger.warning(f"{WordList.TOP1K_RULE_BEST64.name} does not exist. Creating")
        hashcat_stdout = HashcatCmdStdout(outfile=WordList.TOP1K_RULE_BEST64.path)
        hashcat_stdout.add_wordlists(WordList.TOP1K)
        hashcat_stdout.add_rule(Rule.BEST_64)
        subprocess_call(hashcat_stdout.build())


if __name__ == '__main__':
    create_fast_wordlists()