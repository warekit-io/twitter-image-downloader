import argparse
import base64
import json
import os
import shutil

import dateutil.parser
from datetime import datetime
import requests

from . import exceptions as e


class Downloader:
    def __init__(self, api_key, api_secret):
        self.bearer_token = self.bearer(api_key, api_secret)
        self.last_tweet = None
        self.count = 0

    def download_images(self, user, save_dest, size="large", limit=3200, rts=False):
        """Download and save images that user uploaded.

        Args:
            user: User ID.
            save_dest: The directory where images will be saved.
            size: Which size of images to download.
            rts: Whether to include retweets or not.
        """

        if not os.path.isdir(save_dest):
            raise e.InvalidDownloadPathError()

        num_tweets_checked = 0
        tweets = self.get_tweets(user, self.last_tweet, limit, rts)
        if not tweets:
            print("Got an empty list of tweets")

        while len(tweets) > 0 and num_tweets_checked < limit:
            for tweet in tweets:
                # create a file name using the timestamp of the image
                timestamp = dateutil.parser.parse(tweet["created_at"]).timestamp()
                timestamp = int(timestamp)
                value = datetime.fromtimestamp(timestamp)
                fname = value.strftime("%Y-%m-%d-%H-%M-%S")

                # save the image
                images = self.extract_image(tweet)
                if images is not None:
                    counter = 0
                    for image in images:
                        if counter == 0:
                            self.save_image(image, save_dest, fname, size)
                        else:
                            self.save_image(
                                image, save_dest, fname + "_" + str(counter), size
                            )
                        counter += 1
                num_tweets_checked += 1
                self.last_tweet = tweet["id"]

            tweets = self.get_tweets(user, self.last_tweet, count=limit)

        print("\nDone: {} images downloaded".format(self.count))

    def bearer(self, key, secret):
        """Receive the bearer token and return it.

        Args:
            key: API key.
            secret: API string.
        """

        # setup
        credential = base64.b64encode(
            bytes("{}:{}".format(key, secret), "utf-8")
        ).decode()
        url = "https://api.twitter.com/oauth2/token"
        headers = {
            "Authorization": "Basic {}".format(credential),
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        }
        payload = {"grant_type": "client_credentials"}

        # post the request
        r = requests.post(url, headers=headers, params=payload)

        # check the response
        if r.status_code == 200:
            return r.json()["access_token"]
        else:
            raise e.BearerTokenNotFetchedError()

    def get_tweets(self, user, start=None, count=200, rts=False):
        """Download user's tweets and return them as a list.

        Args:
            user: User ID.
            start: Tweet ID.
            rts: Whether to include retweets or not.
        """

        # setup
        bearer_token = self.bearer_token
        url = "https://api.twitter.com/1.1/statuses/user_timeline.json"
        headers = {"Authorization": "Bearer {}".format(bearer_token)}
        payload = {
            "screen_name": user,
            "count": count,
            "include_rts": rts,
            "tweet_mode": "extended",
        }
        if start:
            payload["max_id"] = start

        # get the request
        r = requests.get(url, headers=headers, params=payload)

        # check the response
        if r.status_code == 200:
            tweets = r.json()
            if len(tweets) == 1:
                return []
            else:
                return tweets if not start else tweets[1:]
        else:
            print(
                "An error occurred with the request, the status code was {}".format(
                    r.status_code
                )
            )
            return []

    def extract_image(self, tweet):
        """Return a list of url(s) which represents the image(s) embedded in tweet.

        Args:
            tweet: A dict object representing a tweet.
        """

        if "media" in tweet["entities"]:
            urls = [x["media_url"] for x in tweet["entities"]["media"]]
            if "extended_entities" in tweet:
                extra = [x["media_url"] for x in tweet["extended_entities"]["media"]]
                urls = set(urls + extra)
            return urls
        else:
            return None

    def save_image(self, image, path, timestamp, size="large"):
        """Download and save an image to path.

        Args:
            image: The url of the image.
            path: The directory where the image will be saved.
            timestamp: The time that the image was uploaded.
                It is used for naming the image.
            size: Which size of images to download.
        """

        def print_status(s):
            import sys

            sys.stdout.write(u"\u001b[1K")
            print("\r{} {}".format(["-", "\\", "|", "/"][self.count % 4], s), end="")

        if image:
            # image's path with a new name
            ext = os.path.splitext(image)[1]
            name = timestamp + ext
            save_dest = os.path.join(path, name)

            # save the image in the specified directory if
            if not (os.path.exists(save_dest)):

                r = requests.get(image + ":" + size, stream=True)
                if r.status_code == 200:
                    with open(save_dest, "wb") as f:
                        r.raw.decode_content = True
                        shutil.copyfileobj(r.raw, f)
                    self.count += 1
                    print_status("{} saved".format(name))

            else:
                print_status("Skipping {}: already downloaded".format(name))


def main():
    parser = argparse.ArgumentParser(
        description="Download all images uploaded by a specified Twitter user."
    )
    parser.add_argument("user_id", help="Twitter user ID.")
    parser.add_argument(
        "-c", "--confidentials", help="A json file containing API keys."
    )
    parser.add_argument(
        "-d",
        "--dest",
        help="Specify where to put images. "
        + 'If not specified, a directory named "user_name" will be created '
        + "and images are saved to that directory.",
        default="",
    )
    parser.add_argument(
        "-s",
        "--size",
        help="Specify the size of images.",
        default="large",
        choices=["large", "medium", "small", "thumb", "orig"],
    )
    parser.add_argument(
        "-l",
        "--limit",
        type=int,
        help="The maximum number of tweets to check.",
        default=3200,
    )
    parser.add_argument(
        "--rts", help="Save images contained in retweets.", action="store_true"
    )
    args = parser.parse_args()

    if args.confidentials:
        with open(args.confidentials) as f:
            confidentials = json.loads(f.read())
        if "api_key" not in confidentials or "api_secret" not in confidentials:
            raise e.ConfidentialsNotSuppliedError()
        api_key = confidentials["api_key"]
        api_secret = confidentials["api_secret"]
    else:
        raise e.ConfidentialsNotSuppliedError()

    user = args.user_id
    dest = args.dest
    if len(dest) == 0:
        if not os.path.exists(user):
            os.makedirs(user)
        dest = user

    downloader = Downloader(api_key, api_secret)
    downloader.download_images(user, dest, args.size, args.limit, args.rts)
