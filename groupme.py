import json
import os

import dataset
import requests
from dataset import Table
from tqdm import tqdm


class GroupMe:
    def __init__(self, db, config_dict):
        self.key = config_dict.get('auth_key')
        if not self.key:
            raise Exception("No auth_key set!")

        self.gid = config_dict.get('group_id')
        if not self.gid:
            raise Exception("No group_id set!")

        r = requests.get("https://api.groupme.com/v3/groups", params={"token": self.key})
        if r.status_code is not 200:
            raise Exception("GroupMe API did not respond!")

        self.group_url = "https://api.groupme.com/v3/groups/{}".format(self.gid)
        self.messages_url = "https://api.groupme.com/v3/groups/{}/messages".format(self.gid)

        self.message_table: Table = db['Message']
        self.user_table: Table = b['User']

    def receive_message(self, message):
        if message["system"] or message["text"] is None:
            return
        elif message["sender_type"] == u'bot':
            return
        elif message["text"].startswith("/bot"):
            # ignore bot commands
            return

        self.message_table.insert({
            "message_id": message['id'],
            "user_id": message['user_id'],
            "text": message['text'],
            "favorited_by": json.dumps(message["favorited_by"]),
            "timestamp": message['created_at'],
            "group_id": message['group_id'],
            "object": json.dumps(message),  # just in case
        })

    def refresh_messages(self):
        most_recent_message = self.message_table.find_one(order_by='-timestamp')
        most_recent_id = most_recent_message['message_id']

        r = requests.get(self.messages_url, params={'token': self.key, 'limit': 100, 'after_id': most_recent_id})
        while r.status_code is 200:
            messages = r.json()['response']['messages']
            if not messages:
                return

            for message in r.json()['response']['messages']:
                self.receive_message(message)

            last_id = messages[-1]['id']
            r = requests.get(self.messages_url, params={'token': self.key, 'limit': 100, 'after_id': last_id})

    def recreate_messages(self):
        self.message_table.delete()

        r = requests.get(self.messages_url, params={"token": self.key, "limit": 100})
        count = r.json()['response']['count']
        pbar = tqdm(total=count)

        while r.status_code is 200:
            messages = r.json()['response']['messages']

            if not messages:
                return

            for message in messages:
                self.receive_message(message)

            last_id = messages[-1]["id"]
            r = requests.get(self.messages_url, params={"token": self.key, "limit": 100, "before_id": last_id})
            pbar.update(len(messages))

        pbar.close()

    def recreate_all_names(self):
        r = requests.get("https://api.groupme.com/v3/groups/{}".format(self.gid), params={"token": self.key})
        resp = r.json()["response"]

        for member in resp["members"]:
            self.user_table.insert({
                'user_id': member['user_id'],
                'name': member['nickname'],
                'group_id': self.gid,
                'object': json.dumps(member)
            })

    def messages(self):
        return self.message_table.find()

    def names(self):
        return self.user_table.find()


if __name__ == "__main__":
    filename = os.path.join(os.path.dirname(__file__), "config.json")
    with open(filename, "r") as config_file:
        config_dict = json.loads(config_file.read())

    db = dataset.connect()
    gm = GroupMe(db, config_dict)
    gm.recreate_all_names()
    gm.recreate_messages()
