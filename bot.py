import argparse
import json
import os

import bottle
import dataset
import requests

from analyzer import Analyzer
from gen import Generator
from groupme import GroupMe

LIMIT = 450

# note: must set DATABASE env variable to, e.g., "mysql+pymysql://user:password@localhost/mydatabase"
db = dataset.connect()

HELP_MESSAGE = """Hi! I'm a simple GroupMe bot. Here's what I can do:
/bot ping: returns "hello world"
/bot mimic <x>: returns a random sentence, based on what <x> has said
/bot words: returns most common words
/bot words for <x>: takes a name and gets their words
/bot likes from <x>: gets list of people <x> has liked
/bot likes to <x>: gets list of people who like <x>
/bot ego: gets list of people who've liked their own messages
/bot rank: ranks everyone
/bot rank <x>: ranks <x> overall
/bot ratio for <x>: likes received/message sent
/bot find me true love: finds you true love <3
/bot help: prints this message

Replace <x> with a real name (e.g., /bot mimic Rohan Ramchand) or "me" (i.e., /bot mimic me).
"""


def _unrecognized_directive(message):
    return "Unrecognized command {}. Try /bot help.".format(message['text'])


def _unrecognized_command(message, expected):
    return "Unrecognized command {}. Did you mean {}?".format(message['text'], expected)


def _unrecognized_user(name):
    return "Unknown user {}.".format(name)


def _error(exception):
    return "Oops! We fucked up. Here's the error: {}".format(exception)


def _process(message):
    return message['text'].strip().split(" ")


def _format_rank(rank):
    if rank == -1:
        return "(not ranked)"

    return {
        1: '{}st',
        2: '{}nd',
        3: '{}rd',
    }.get(rank, '{}th').format(rank)


class BotEngine(bottle.Bottle):
    def __init__(self, config_dict, analyzer: Analyzer, generator: Generator, database: GroupMe, console_mode=False):
        super(BotEngine, self).__init__()
        self.post('/groupme/callback', callback=self.receive)

        self.bot_id = config_dict.get('bot_id')
        if not self.bot_id:
            raise Exception("No bot_id found!")

        self.analyzer = analyzer
        self.generator = generator
        self.database = database

        self.console_mode = console_mode

    def ping(self, message):
        return "Hello, world!"

    def mimic(self, message):
        command = _process(message)
        if len(command) < 3:
            return _unrecognized_command(message, "/bot mimic {name}")

        name = " ".join(command[2:])
        uid = message['user_id'] if name == "me" else self.database.get_uid(name)
        if not uid:
            return _unrecognized_user(name)

        return "{}: \"{}\"".format(self.database.get_name(uid), self.generator.generate(uid, 30, cut=False))

    def words(self, message):
        command = _process(message)
        if len(command) == 2:
            words = self.analyzer.most_common_words
            return "Most common words: {}".format(", ".join(
                sorted(words, key=lambda word: sum(words[word].values()), reverse=True)[:15]))

        if len(command) == 3:
            return _unrecognized_command(message, "/bot words or /bot words for {name}")

        name = " ".join(command[3:])
        uid = message['user_id'] if name == "me" else self.database.get_uid(name)
        if not uid:
            return _unrecognized_user(name)

        words = self.analyzer.mcw_per_user[uid]
        return "Most common words for {}: {}".format(
            self.database.get_name(uid), ", ".join(sorted(words, key=words.get, reverse=True)[:15]))

    def likes(self, message):
        command = _process(message)
        if len(command) < 4:
            return _unrecognized_command(message, "/bot likes from {user} or /bot likes to {user}")

        name = " ".join(command[3:])
        uid = message['user_id'] if name == "me" else self.database.get_uid(name)
        if not uid:
            return _unrecognized_user(name)

        direction = command[2]
        if direction == "from":
            liked = self.analyzer.user_likes[uid]
            return "{} has liked a total of {} messages, most frequently from: {}".format(
                self.database.get_name(uid), sum(liked.values()), ", ".join([
                    self.database.get_name(_uid) for _uid in sorted(liked, key=liked.get, reverse=True)[:15]]))
        elif direction == "to":
            likes = self.analyzer.likes_per_user[uid]
            return "{} has received {} likes, most frequently from: {}".format(
                self.database.get_name(uid), sum(likes.values()), ", ".join([
                    self.database.get_name(_uid) for _uid in sorted(likes, key=likes.get, reverse=True)[:15]]))
        else:
            return _unrecognized_command(message, "/bot likes from {user} or /bot likes to {user}")

    def ratio(self, message):
        command = _process(message)
        if len(command) < 4:
            return _unrecognized_command(message, "/bot ratio for {user}")

        name = " ".join(command[3:])
        uid = message['user_id'] if name == "me" else self.database.get_uid(name)
        if not uid:
            return _unrecognized_user(name)

        likes = self.analyzer.likes_per_user[uid]
        messages = self.analyzer.messages_by_user[uid]

        return "{} has a likes/messages ratio of {:.2f}.".format(
            self.database.get_name(uid), float(sum(likes.values())) / len(messages))

    def ego(self, message):
        template = "{} has liked their own posts {} time(s)."
        return "\n".join(
            template.format(self.database.get_name(uid), likes) for uid, likes in self.analyzer.get_self_likes())

    def rank(self, message):
        command = _process(message)
        if len(command) == 2:
            return """Most likes sent: {}
            Most likes received: {}
            Highest like/message ratio: {}""".format(
                ", ".join(["{} ({})".format(self.database.get_name(uid), value) for uid, value in
                           self.analyzer.get_most_overall_likes_sent()]),
                ", ".join(["{} ({})".format(self.database.get_name(uid), value) for uid, value in
                           self.analyzer.get_most_overall_likes_recd()]),
                ", ".join(["{} ({})".format(self.database.get_name(uid), value) for uid, value in
                           self.analyzer.get_highest_overall_ratio()])
            )

        name = " ".join(command[2:])
        uid = message['user_id'] if name == "me" else self.database.get_uid(name)
        if not uid:
            return _unrecognized_user(name)

        likes_sent, sent_rank = self.analyzer.get_likes_sent_and_rank(uid)
        likes_recd, recd_rank = self.analyzer.get_likes_received_and_rank(uid)
        ratio, ratio_rank = self.analyzer.get_ratio_and_rank(uid)

        return """Messages {name} sent that people have liked: {like_recd_count} ({like_recd_rank} overall)
        Messages people have sent that {name} liked: {like_sent_count} ({like_sent_rank} overall)
        Like/message ratio: {ratio:.2f} ({ratio_rank} overall)
                """.format(
            name=self.database.get_name(uid),
            like_recd_count=likes_recd, like_recd_rank=_format_rank(recd_rank),
            like_sent_count=likes_sent, like_sent_rank=_format_rank(sent_rank),
            ratio=ratio, ratio_rank=_format_rank(ratio_rank)
        )

    def receive(self, msg=None):
        msg = msg or bottle.request.json
        text = msg["text"]
        if not text.startswith("/bot"):
            # read this in as a normal message
            msg["favorited_by"] = []
            self.database.receive_message(msg)
            self.analyzer.read_message(msg)
            self.generator.read_message(msg)
            return

        if text == "/bot find me true love":
            return self.send_message(
                "I can't provide love, but I can provide the next best thing: http://lmgtfy.com/?q=porn")

        command = _process(msg)
        directive = command[1]

        fn = {
            'ping': self.ping,
            'mimic': self.mimic,
            'words': self.words,
            'likes': self.likes,
            'ratio': self.ratio,
            'ego': self.ego,
            'rank': self.rank,
            'help': lambda *args, **kwargs: HELP_MESSAGE,
        }.get(directive, _unrecognized_directive)

        try:
            return self.send_message(fn(msg))
        except Exception as e:
            return self.send_message(_error(e))

    def send_message(self, message):
        words = message.split(" ")
        splits = []
        current = ""
        count = 0

        for word in words:
            if count + len(word) >= LIMIT:
                splits += [current]
                count = 0
                current = ""
            current += word + " "
            count += len(word)

        splits += [current]

        for split in splits[:5]:
            if self.console_mode:
                print(split)
            else:
                requests.post("https://api.groupme.com/v3/bots/post", {"bot_id": self.bot_id, "text": split})


def main(console_mode=False):
    filename = os.path.join(os.path.dirname(__file__), "config.json")
    with open(filename, "r") as config_file:
        config_dict = json.loads(config_file.read())

    db = dataset.connect()
    database = GroupMe(db, config_dict)
    analyzer = Analyzer(database)
    generator = Generator(7, database)

    database.refresh_messages()
    analyzer.rebuild()
    generator.rebuild()

    bot = BotEngine(config_dict, analyzer, generator, database, console_mode=console_mode)
    if console_mode:
        while True:
            cmd = input("Enter your command: ")
            bot.receive({'text': cmd, 'favorited_by': [], 'user_id': "6744840"})
    else:
        bot.run(host='0.0.0.0')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run GroupMe bot.')
    parser.add_argument(
        '--console', dest='console_mode', type=bool, action='store_const', const=True, help="Run in console mode.")
    args = parser.parse_args()
    main(console_mode=args.console_mode)
