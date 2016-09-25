from collections import defaultdict
import random
import requests
import sys, os
from datetime import datetime
import string

import pprint

import bottle
#GROUP_ID = "25323255" 
GROUP_ID = "11436795"
BOT_ID = "34cd6ae9e58a5c32f24d310cff"

def progress(cur, tot):
  out = str(cur) + " of " + str(tot) + " messages downloaded"
  sys.stdout.write('%s\r' % out)
  sys.stdout.flush()

# this class can *only* read from the group the bot has access to
class GroupMe():
  def __init__(self, token_file):
    with open(token_file) as f:
      self.key = f.readline().replace("\n", "")

    # get all groups I'm a part of
    if self.key is None:
      print "get_groups: unable to find key."
      return

    r = requests.get("https://api.groupme.com/v3/groups",
        params = {"token": self.key})
    if r.status_code is not 200:
      print "get_groups: couldn't read from GroupMe endpoint"
      return

    global GROUP_ID
    self.gid = GROUP_ID

  def get_all_messages(self):
    print "Reading messages..."
    r = requests.get("https://api.groupme.com/v3/groups/"
        + self.gid + "/messages",
        params = {"token": self.key, "limit": 100})
    message_count = r.json()["response"]["count"]

    i = 0
    out = []

    while r.status_code is 200 and i < message_count:
      progress(i, message_count)
      resp = r.json()["response"]
      messages = resp["messages"]

      for message in messages:
        if message["system"] or message["text"] is None:
          continue
        if message["sender_type"] == u'bot':
          continue

        # ignore bot commands
        if message["text"].startswith("/bot"):
          continue
        out += [message]

      i += len(messages)

      last_id = messages[-1]["id"]
      r = requests.get("https://api.groupme.com/v3/groups/"
          + self.gid + "/messages",
          params = {"token": self.key, "limit": 100, "before_id": last_id})

    return out

  def get_all_names(self):
    r = requests.get("https://api.groupme.com/v3/groups/" + self.gid,
        params = {"token": self.key})
    if r.status_code is not 200:
      print "get_all_names: couldn't read from the GroupMe endpoint"
      return

    resp = r.json()["response"]
    out = defaultdict(lambda : "(former member)")

    for member in resp["members"]:
      out[member["user_id"]] = member["nickname"]

    return out

class Analyzer():
  # messages is passed in raw from GroupMe
  def __init__(self, names, messages):
    self.names = names
    self.messages = messages
    # do some preanalysis

    # MBU: user_id -> [message]
    self.messages_by_user = defaultdict(list)

    # who has liked {{user}}'s messages?
    # user_id -> (liker -> count)
    self.likes_per_user = defaultdict(lambda : defaultdict(int))

    # who has {{user}} liked?
    # user_id -> (liked -> count)
    self.user_likes = defaultdict(lambda : defaultdict(int))

    # which words are used most often?
    # word -> (user_id -> count)
    self.most_common_words = defaultdict(lambda : defaultdict(int))

    # per user, which words are used most often?
    # user_id -> (word -> count)
    self.mcw_per_user = defaultdict(lambda : defaultdict(int))

    # which users have liked their own posts?
    # user_id -> count
    self.self_likes = defaultdict(int)

    for message in messages:
      sender = message["user_id"]
      self.messages_by_user[sender] += [message]
      
      text = message["text"]
      for word in text.split(" "):
        word = self.translate_non_alphanumerics(word, translate_to=u"").lower()
        self.most_common_words[word][sender] += 1
        self.mcw_per_user[sender][word] += 1
      
      for liker in message["favorited_by"]:
        self.user_likes[liker][sender] += 1
        self.likes_per_user[sender][liker] += 1

        if liker == sender:
          self.self_likes[sender] += 1

  def translate_non_alphanumerics(self, to_translate, translate_to=u'_'):
    not_letters_or_digits = u'!"#%\'()*+,-./:;<=>?@[\]^_`{|}~'
    translate_table = dict((ord(char), translate_to)
        for char in not_letters_or_digits)
    return to_translate.translate(translate_table)

class Generator():
  def __init__(self, k, messages):
    self.k = k
    # user_id -> (phrase -> [next words])
    self.m = defaultdict(lambda : defaultdict(list))

    for message in messages:
      self.read_input(message["text"], message["user_id"],
          len(message["favorited_by"]) + 1)

  def read_input(self, message, sender, likes):
    words = message.split(" ")

    for i in range(len(words) - self.k):
      # store every k-length interval
      window = " ".join(words[i:i+self.k])
      self.m[sender][window] += [words[i+self.k]] * likes

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
        if (i + self.k > length):
          seed = seed[:(length - i)]

        i += self.k
        output += seed
      else:
        output += [random.choice(letters)]

    return " ".join(output)

  def k_random_words(self, speaker):
    keys = self.m[speaker].keys()
    wkeys = []

    for s in keys:
      letters = self.m[speaker][s]
      wkeys += [s] * len(letters)

    return random.choice(wkeys).split(" ")

class BotEngine(bottle.Bottle):
  def __init__(self, bot_id, analyzer, generator):
    super(BotEngine, self).__init__()
    self.post('/groupme/callback', callback=self.receive)
    self.bot_id = bot_id
    self.analyzer = analyzer
    self.generator = generator

  def receive(self):
    msg = bottle.request.json
    sender = msg["name"]
    text = msg["text"]
    sid = msg["user_id"]
    if not text.startswith("/bot"):
      return

    # acceptable commands:
    # /bot ping: returns "hello world"
    # /bot words: returns most common words
    # /bot words for <x>: takes a name and gets their words
    # /bot words for me: gets sender's words
    # /bot likes from <x>: gets list of people <x> has liked
    # /bot likes to <x>: gets list of people who like <x>
    # /bot ego: gets list of people who've liked their own messages

    command = text.split(" ")
    out = ""
    if command[1] == "ping":
      if len(command) == 2:
        out = "Hello, world!"
      else:
        out = "Unrecognized command " + text + ". Ignoring."

    elif command[1] == "mimic":
      if len(command) >= 3:
        if command[2] == "me":
          out = self.mimic(sid)
        else:
          uid = self.get_uid(" ".join(command[2:]))
          if uid is None:
            out = "Unable to find user " + " ".join(command[2:]) + "."
          else:
            out = self.mimic(uid)
      else:
        out = "Unrecognized command " + text + ". Ignoring."
    elif command[1] == "words":
      if len(command) == 2:
        out = self.most_common_words()
      elif len(command) >= 4:
        if command[3] == "me":
          out = self.most_common_words_for_user(sid) 
        else:
          uid = self.get_uid(" ".join(command[3:]))
          if uid is None:
            out = "Unable to find user " + " ".join(command[3:]) + "."
          else:
            out = self.most_common_words_for_user(uid)
      else:
        out = "Unrecognized command " + text + ". Ignoring."
    elif command[1] == "likes":
      if len(command) >= 4:
        if command[2] == "from":
          if command[3] == "me":
            out = self.likes_from(sid)
          else:
            uid = self.get_uid(" ".join(command[3:]))
            if uid is None:
              out = "Unable to find user " + " ".join(command[3:]) + "."
            else:
              out = self.likes_from(uid)

        elif command[2] == "to":
          if command[3] == "me":
            out = self.likes_to(sid)
          else:
            uid = self.get_uid(" ".join(command[3:]))
            if uid is None:
              out = "Unable to find user " + " ".join(command[3:]) + "."
            else:
              out = self.likes_to(uid)
        else:
          out = "Unrecognized command " + text + ". Ignoring."
      else:
        out = "Unrecognized command " + text + ". Ignoring."
    elif command[1] == "ego":
      if len(command) == 2:
        out = self.self_likers()
      else:
        out = "Unrecognized command " + text + ". Ignoring."
    elif command[1] == "help":
      out = """Hi! I'm a simple GroupMe bot. Here's what I can do:
/bot ping: returns "hello world"
/bot mimic <x>: returns a random sentence, based on what <x> has said
/bot words: returns most common words
/bot words for <x>: takes a name and gets their words
/bot words for me: gets sender's words
/bot likes from <x>: gets list of people <x> has liked
/bot likes to <x>: gets list of people who like <x>
/bot ego: gets list of people who've liked their own messages
/bot help: prints this message
"""
    else:
      out = "Unrecognized command " + text + ". Ignoring."

    r = requests.post("https://api.groupme.com/v3/bots/post",
        {"bot_id": self.bot_id, "text": out})
      
  def most_common_words(self):
    out = "Most common words:\n"
    words = self.analyzer.most_common_words
    names = self.analyzer.names

    for word in sorted(words,
        key=lambda word : sum(words[word].values()),
        reverse=True):
      out += "\t" + word + ": " + str(sum(words[word].values())) + " (most frequently by "

      most_common = [names[nid] + " [" + str(words[word][nid]) + "]"
          for nid in sorted(words[word], key=words[word].get, reverse=True)]
      out += ", ".join(most_common) + ")\n"

    return out

  def get_uid(self, name):
    names = self.analyzer.names
    reversed_names = { v : k for (k,v) in names.iteritems() }
    if name not in reversed_names:
      return None
    return reversed_names[name]

  def most_common_words_for_user(self, uid):
    names = self.analyzer.names
    words = self.analyzer.mcw_per_user[uid]
    out = "Most common words for " + names[uid] + ":\n"

    out += "\n  ".join([word + " [" + str(words[word]) + "]"
      for word in sorted(words, key=words.get, reverse=True)])

    out += "\n"
    return out

  def likes_from(self, uid):
    names = self.analyzer.names
    liked = self.analyzer.user_likes[uid]

    out = names[uid] + " has liked a total of " + str(sum(liked.values())) + " messages, most frequently from:\n"

    out += "\n".join([names[uid] + " [" + str(liked[uid]) + "]" for uid in
      sorted(liked, key=liked.get, reverse=True)])
    out += "\n"

    return out

  def likes_to(self, uid):
    names = self.analyzer.names
    likes = self.analyzer.likes_per_user[uid]

    out = names[uid] + "'s messages have been liked a total of " + str(sum(likes.values())) + " times, most frequently by:\n"

    out += "\n".join([names[uid] + " [" + str(likes[uid]) + "]" for uid in
      sorted(likes, key=likes.get, reverse=True)])
    out += "\n"

    return out

  def self_likers(self):
    names = self.analyzer.names
    likes = self.analyzer.self_likes
    out = ""

    for uid in sorted(likes, key=likes.get, reverse=True):
      out += names[uid] + " has liked their own posts "
      if likes[uid] == 1:
        out += str(likes[uid]) + " time.\n"
      else:
        out += str(likes[uid]) + " times.\n"

    return out

  def mimic(self, uid):
    names = self.analyzer.names
    out = names[uid]
    out += ": \"" + self.generator.generate(uid, 30, cut=True) + "\""
    return out

convo = GroupMe("./auth_key")
names = convo.get_all_names()
messages = convo.get_all_messages()

analyzer = Analyzer(names, messages)
generator = Generator(7, messages)

bot = BotEngine(BOT_ID, analyzer, generator)
bot.run(host='0.0.0.0', port=8080)

