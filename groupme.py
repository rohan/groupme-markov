from collections import defaultdict
import random
import requests
import sys, os
import cPickle as pickle
from datetime import datetime
import string

class RandomWriter():
  def __init__(self, k, depickle=True):
    self.k = k
    self.m = None
    if depickle:
      self.m = self.depickle_me()
      self.depickled = True
    
    if self.m == None:
      self.m = {}
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

    names = defaultdict(str)
    exclamations = defaultdict(int)
    exclamation_density = defaultdict(list)

    t_likes = defaultdict(int)
    t_like_avg = defaultdict(list)
    
    liked_by = defaultdict(lambda : defaultdict(int))
    user_likes = defaultdict(lambda : defaultdict(int))

    most_common_words = defaultdict(int)
    mcw_per_user = defaultdict(lambda : defaultdict(int))

    while r.status_code is 200 and i < message_count:
      resp = r.json()["response"]
      messages = resp["messages"]
      for message in messages:
        if message["system"] or message["text"] is None:
          continue

        if names[message["user_id"]] == "":
          names[message["user_id"]] = message["name"]

        text = message["text"]
        exclamations[message["user_id"]] += text.count("!")
        exclamation_density[message["user_id"]].append(text.count("!") /
            float(len(text)))

        for word in text.split(" "):
          word = self.translate_non_alphanumerics(word, translate_to=u"").lower()
          most_common_words[word] += 1
          mcw_per_user[message["user_id"]][word] += 1

        if len(text.split(" ")) < self.k:
          continue

        for liking_user in message["favorited_by"]:
          liked_by[message["user_id"]][liking_user] += 1
          user_likes[liking_user][message["user_id"]] += 1
        
        likes = len(message["favorited_by"]) # don't ignore 0 likes
        t_likes[message["user_id"]] += likes
        t_like_avg[message["user_id"]].append(likes)

        self.read_input((text, likes+1))
      
      last_id = messages[-1]["id"]
      r = requests.get("https://api.groupme.com/v3/groups/" + self.gid +
          "/messages", params={"token": self.key, "before_id": last_id, "limit":
            100})

    for (k,v) in sorted(exclamations.iteritems(), key=lambda (k,v): v,
        reverse=True):
      d = exclamation_density[k]
      print names[k] + ": " + str(exclamations[k]) + " " + \
      str(sum(d) / len(d))

    print "\n*** LIKES ***"
    for (k,v) in sorted(t_likes.iteritems(), key=lambda (k,v): v, reverse=True):
      l = t_like_avg[k]
      print names[k] + ": " + str(t_likes[k]) + " " + \
      str(sum(l) / float(len(l)))

    print "\n*** LIKE ASSOCIATIONS ***"
    print "User -> Users who liked their post"
    self_likers = []
    for (user, likes_from) in sorted(liked_by.iteritems(), key=lambda (k,v):
        sum(v.values()), reverse=True):
      # users this user has received likes FROM
      print "User:", names[user], "(" + str(sum(likes_from.values())) + ")"
      for (liker, count) in sorted(likes_from.iteritems(), key=lambda (k,v): v,
          reverse=True):
        print "\t" + names[liker] + ": " + str(count)
        if user == liker: self_likers.append((names[user], count))

    print "\nUser -> Users whose posts they liked"
    for (user, likes_to) in sorted(user_likes.iteritems(), key=lambda (k,v):
        sum(v.values()), reverse=True):
      # users this user has given likes TO
      print "User:", names[user], "(" + str(sum(likes_to.values())) + ")"
      for (liking, count) in sorted(likes_to.iteritems(), key=lambda (k,v): v,
          reverse=True):
        print "\t" + names[liking] + ": " + str(count)

    print "\n*** SELF-LIKERS ***"
    for sl in self_likers:
      print sl[0] + ": " + str(sl[1])


    print "\n***MOST COMMON WORDS***"
    with open("mcw.txt", "w") as f:
      for (w, c) in sorted(most_common_words.iteritems(), key=lambda (k,v): v,
          reverse=True):
        line = w + ": " + str(c) + "\n"
        f.write(line.encode("utf-8"))

    with open("mcw_per_user.txt", "w") as f:
      for user in mcw_per_user.keys():
        line = names[user] + "\n"
        f.write(line.encode("utf-8"))
        for (word, count) in sorted(mcw_per_user[user].iteritems(), key=lambda (k,v):
            v, reverse=True):
          line = "\t" + word + ": " + str(count) + "\n"
          f.write(line.encode("utf-8"))

    if pickle:
      self.pickle_me()

  def translate_non_alphanumerics(self, to_translate, translate_to=u'_'):
      not_letters_or_digits = u'!"#%\'()*+,-./:;<=>?@[\]^_`{|}~'
      translate_table = dict((ord(char), translate_to) for char in not_letters_or_digits)
      return to_translate.translate(translate_table)

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
