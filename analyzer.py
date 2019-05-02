import json
from collections import defaultdict
from operator import itemgetter

from typing import Dict, Any, Optional

from groupme import GroupMe

IGNORE = ['the', 'be', 'to', 'of', 'and', 'a', 'in', 'that', 'have', 'I', 'it',
          'for', 'not', 'on', 'with', 'he', 'as', 'you', 'do', 'at', 'this', 'but',
          'his', 'by', 'from', 'they', 'we', 'say', 'her', 'she', 'or', 'an', 'will',
          'my', 'one', 'all', 'would', 'there', 'their', 'what', 'so', 'up', 'out',
          'if', 'about', 'who', 'get', 'which', 'go', 'me', 'when', 'make', 'can',
          'like', 'time', 'no', 'just', 'him', 'know', 'take', 'person', 'into',
          'year', 'your', 'good', 'some', 'could', 'them', 'see', 'other', 'than',
          'then', 'now', 'look', 'only', 'come', 'its', 'over', 'think', 'also',
          'back', 'after', 'use', 'two', 'how', 'our', 'work', 'first', 'well', 'way',
          'even', 'new', 'want', 'because', 'any', 'these', 'give', 'day', 'most',
          'us', '']


def translate_non_alphanumerics(to_translate, translate_to=u'_'):
    not_letters_or_digits = '!"#%\'()*+,-./:;<=>?@[\\]^_`{|}~'
    translate_table = dict((ord(char), translate_to)
                           for char in not_letters_or_digits)
    return to_translate.translate(translate_table)


def rank_in_dict(d: Dict[str, Any], key: str) -> int:
    # given a dict from uid -> value, find the rank of uid in dict
    return sorted(d, key=lambda k: d[k], reverse=True).index(key) + 1 if key in d else -1


class Analyzer:
    # messages is passed in raw from GroupMe
    def __init__(self, database: GroupMe):
        self.database = database
        # MBU: user_id -> [message]
        self.messages_by_user = defaultdict(list)

        # who has liked {{user}}'s messages?
        # user_id -> (liker -> count)
        self.likes_per_user = defaultdict(lambda: defaultdict(int))

        # who has {{user}} liked?
        # user_id -> (liked -> count)
        self.user_likes = defaultdict(lambda: defaultdict(int))

        # which words are used most often?
        # word -> (user_id -> count)
        self.most_common_words = defaultdict(lambda: defaultdict(int))

        # per user, which words are used most often?
        # user_id -> (word -> count)
        self.mcw_per_user = defaultdict(lambda: defaultdict(int))

        # which users have liked their own posts?
        # user_id -> count
        self.self_likes = defaultdict(int)

    def rebuild(self):
        for message in self.database.messages():
            self.read_message(message)

    def read_message(self, message):
        sender = message["user_id"]
        self.messages_by_user[sender] += [message]

        text = message["text"]
        for word in text.split(" "):
            word = translate_non_alphanumerics(word, translate_to=u"").lower()
            if word in IGNORE:
                continue
            self.most_common_words[word][sender] += 1
            self.mcw_per_user[sender][word] += 1

        for liker in json.loads(message["favorited_by"]):
            self.user_likes[liker][sender] += 1
            self.likes_per_user[sender][liker] += 1

            if liker == sender:
                self.self_likes[sender] += 1

    def get_self_likes(self, limit=15):
        return [(uid, self.self_likes[uid]) for uid in sorted(
            self.self_likes, key=self.self_likes.get, reverse=True)[:limit]]

    def get_likes_sent_and_rank(self, uid):
        likes_sent_per_user: Dict[str, int] = {k: sum(self.user_likes[k].values()) for k in self.user_likes}
        return likes_sent_per_user[uid], rank_in_dict(likes_sent_per_user, uid)

    def get_most_overall_likes_sent(self):
        likes_sent_per_user: Dict[str, int] = {k: sum(self.user_likes[k].values()) for k in self.user_likes}
        return sorted(likes_sent_per_user.items(), key=itemgetter(1), reverse=True)

    def get_likes_received_and_rank(self, uid):
        likes_recd_per_user: Dict[str, int] = {k: sum(self.likes_per_user[k].values()) for k in self.likes_per_user}
        return likes_recd_per_user[uid], rank_in_dict(likes_recd_per_user, uid)

    def get_most_overall_likes_recd(self):
        likes_recd_per_user: Dict[str, int] = {k: sum(self.likes_per_user[k].values()) for k in self.likes_per_user}
        return sorted(likes_recd_per_user.items(), key=itemgetter(1), reverse=True)

    def get_ratio_and_rank(self, uid):
        ratios_per_user: Dict[str, float] = {
            k: float(sum(self.likes_per_user[k].values())) / len(self.messages_by_user[k]) for k in self.likes_per_user}
        return ratios_per_user[uid], rank_in_dict(ratios_per_user, uid)

    def get_highest_overall_ratio(self):
        ratios_per_user: Dict[str, float] = {
            k: float(sum(self.likes_per_user[k].values())) / len(self.messages_by_user[k]) for k in self.likes_per_user}
        return sorted(ratios_per_user.items(), key=itemgetter(1), reverse=True)
