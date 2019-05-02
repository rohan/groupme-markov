import json
import random
from collections import defaultdict

from groupme import GroupMe


class Generator:
    def __init__(self, k, database: GroupMe):
        self.database = database
        self.k = k
        # user_id -> (phrase -> [next words])
        self.m = defaultdict(lambda: defaultdict(list))

    def rebuild(self):
        for message in self.database.messages():
            self.read_message(json.loads(message['object']))

    def read_message(self, message):
        text = message['text']
        sender = message['user_id']
        likes = len(message['favorited_by'])
        words = text.split(" ")

        for i in range(len(words) - self.k):
            # store every k-length interval
            window = " ".join(words[i:i + self.k])
            self.m[sender][window] += [words[i + self.k]] * (likes + 1)

        # make sure the last interval exists as well
        window = " ".join(words[(-1 * self.k):])
        # the 2nd self.m[window] will either preserve or set to [] the first
        self.m[sender][window] = self.m[sender][window]

    def generate(self, uid, length, cut=False):
        output = self.k_random_words(uid)

        for i in range(self.k, length):
            window = " ".join(output[(i - self.k):])
            letters = self.m[uid][window]

            if len(letters) == 0:
                if cut:
                    return output
                seed = self.k_random_words(uid)
                if i + self.k > length:
                    seed = seed[:(length - i)]

                i += self.k
                output += seed
            else:
                output += [random.choice(letters)]

        print(output)
        return " ".join(output).encode('utf8')

    def k_random_words(self, speaker):
        keys = self.m[speaker].keys()
        wkeys = []

        for s in keys:
            letters = self.m[speaker][s]
            wkeys += [s] * len(letters)

        return random.choice(wkeys).split(" ")
