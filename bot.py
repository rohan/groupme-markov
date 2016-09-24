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


class GroupMe():
  def __init__(self, auth_key_file, group_name):
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

    resp = r.json()["response"]
    for group in resp:
      if group["name"] is group_name:
        self.gid = group["id"]

    self.messages = []

  def get_all_messages(self, group_id):
    r = requests.get("https://api.groupme.com/v3/groups/"
        + group_id + "/messages",
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
        out += [message]

      last_id = messages[-1]["id"]
      r = requests.get("https://api.groupme.com/v3/groups/"
          + group_id + "/messages",
          params = {"token": self.key, "limit": 100, "before_id": last_id})

class Analyzer():
  def __init__(self, messages):
    self.messages = messages
    # do some preanalysis

  pass

class RandomWriter():
  pass


group_name = "Tacopella"
convo = GroupMe("./auth_key", group_name)
messages = convo.get_all_messages()

# messages now contains all messages from group_name
# create a new analyzer
analyzer = Analyzer(messages)

