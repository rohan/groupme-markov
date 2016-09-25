# accepts a GroupMe conversation, formatted as (message, likes)
# supports the following operations:
# mylikes: who have I liked the most?
# likedme: who has liked me the most?
# make <x> talk: generate random sentence from <x>

from collections import defaultdict
import random
import requests
import sys, os
from datetime import datetime
import string

import pprint

import bottle

GROUP_ID = "25323255"

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

    self.messages = []

  def get_all_messages(self):
    r = requests.get("https://api.groupme.com/v3/groups/"
        + self.gid + "/messages",
        params = {"token": self.key, "limit": 100})
    message_count = r.json()["response"]["count"]

    i = 0
    out = []

    while r.status_code is 200 and i < message_count:
      resp = r.json()["response"]
      messages = resp["messages"]

      for message in messages:
        if message["system"] or message["text"] is None:
          continue
        if message["sender_type"] == u'bot':
          continue
        out += [message]

      last_id = messages[-1]["id"]
      r = requests.get("https://api.groupme.com/v3/groups/"
          + self.gid + "/messages",
          params = {"token": self.key, "limit": 100, "before_id": last_id})


    return out

class Analyzer():
  # messages is passed in raw from GroupMe
  def __init__(self, messages):
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

class RandomWriter():
  pass

class BotEngine(bottle.Bottle):
  def __init__(self, bot_id, analyzer):
    super(BotEngine, self).__init__()
    self.post('/groupme/callback', callback=self.receive)
    self.bot_id = bot_id
    self.analyzer = analyzer

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
    elif command[1] == "words":
      if len(command) == 2:
        out = "The most common words are:\n"
        out += self.most_common_words()
      elif len(command) == 4:
        # most common words for <x>
      else:
        out = "Unrecognized command " + text + ". Ignoring."
    elif command[1] == "likes":
      if len(command) == 4:
        # likes
      else:
        out = "Unrecognized comand " + text + ". Ignoring."
    elif command[1] == "ego":
      if len(command) == 2:
        # self-likes
      else:
        out = "Unrecognized command " + text + ". Ignoring."

    r = requests.post("https://api.groupme.com/v3/bots/post",
        {"bot_id": self.bot_id, "text": out})
      
  def most_common_words(self):
    out = ""
    words = self.analyzer.most_common_words
    names = self.analyzer.names

    for key in sorted(words,
        key=lambda word : sum(words[word].values()),
        reverse=True):
      out += "\t" + word + ": " + str(sum(words[word].values())) + " (most frequently
      by "

      most_common = [names[nid] + " [" + str(words[word][nid]) + "]"
          for nid in sorted(words[word], key=words[word].get, reverse=True)]
      out += most_common.join(", ") + ")\n"

    return out

convo = GroupMe("./auth_key")
messages = convo.get_all_messages()
#pprint.pprint(messages)

# messages now contains all messages from group_name
# create a new analyzer
analyzer = Analyzer(messages)

bot = BotEngine(analyzer)
bot.run(host='localhost', 8080)

