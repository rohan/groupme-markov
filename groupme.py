from collections import defaultdict
import random
import requests
import sys, os
import cPickle as pickle
from datetime import datetime

class RandomWriter():
  def __init__(self, k, depickle=True):
    self.k = k
    self.m = None
    if depickle:
      self.m = self.depickle_me()
      self.depickled = True
    
    if self.m == None:
      self.m = defaultdict(list)
      self.depickled = False

  def read_input(self, source):
    # source is formatted as follows:
    # (message, likes)
    
    message, likes = source

    words = message.split(" ")

    for i in range(len(words) - self.k):
      window = " ".join(words[i:i+self.k])
      try:
        letters = self.m[window]
      except KeyError:
        letters = []
      letters += [words[i+self.k]] * likes
      self.m[window] = letters

    window = " ".join(words[(-1 * self.k):])
    try:
      letters = self.m[window]
    except KeyError:
      letters = []

    self.m[window] = letters

  def write_output(self, length, cut=False):
    output = self.k_random_words()

    for i in range(self.k, length):
      window = " ".join(output[(i - self.k):])
      letters = self.m.get(window)

      if (letters == None or letters == []):
        if cut:
          return output
        seed = self.k_random_words()
        if (i + self.k > length):
          seed = seed[:(length - i)]

        i += self.k
        output += seed
      else:
        output += [random.choice(letters)]

    return output
  
  def k_random_words(self):
    keys = self.m.keys()
    wkeys = []

    for s in keys:
      letters = self.m[s]
      wkeys += [s] * len(letters)

    return random.choice(wkeys).split(" ")

  def init_gm(self, token_file, chat_name):
    with open(token_file) as f:
      self.key = f.readline().replace("\n", "")

    r = requests.get("https://api.groupme.com/v3/groups", params={"token":
      self.key})
    if r.status_code is not 200:
      print "Couldn't read from Groupme endpoint"
      exit(1)
    
    resp = r.json()["response"]
    for group in resp:
      if group["name"] == chat_name:
        self.gid = group["id"]
        break

    print "group id: " + self.gid

  def read_messages_from_chat(self, pickle=True):
    r = requests.get("https://api.groupme.com/v3/groups/" + self.gid +
        "/messages", params={"token": self.key, "limit": 100})
    message_count = r.json()["response"]["count"]
    i = 0
    while r.status_code is 200 and i < message_count:
      resp = r.json()["response"]
      messages = resp["messages"]
      for message in messages:
        if message["system"] or message["text"] is None:
          continue
        text = message["text"]
        if len(text.split(" ")) < self.k:
          continue
        likes = len(message["favorited_by"]) + 1 # don't ignore 0 likes
        print text, likes
        self.read_input((text, likes))
      
      last_id = messages[-1]["id"]
      r = requests.get("https://api.groupme.com/v3/groups/" + self.gid +
          "/messages", params={"token": self.key, "before_id": last_id, "limit":
            100})
      sys.stdout.flush()

    if pickle:
      self.pickle_me()

  def pickle_me(self):
    date = datetime.now().strftime("%m-%d-%y %H.%M.%S")
    fn = "k" + str(self.k) + " " + date + ".pickle"
    
    for filename in os.listdir("."):
      if os.path.splitext(filename)[1] == ".pickle":
        if filename.startswith("k" + str(self.k)):
          os.rename(filename, filename + ".old")

    pickle.dump(self.m, open(fn, "wb"))

  def depickle_me(self):
    for filename in os.listdir("."):
      print os.path.splitext(filename)
      if os.path.splitext(filename)[1] == ".pickle":
        print "good"
        if filename.startswith("k" + str(self.k)):
          print "depickling success!"
          return pickle.load(open(filename, "rb"))

    return None


rw = RandomWriter(6, depickle=False)
rw.init_gm("./auth_key", "SONGCHAT")

if not rw.depickled:
  data = rw.read_messages_from_chat()

print " ".join(rw.write_output(30))
