import requests
import sys
import spotipy
import tidalapi
import time
import traceback

async def repeat_on_request_error(function, *args, remaining=5, **kwargs):
    # utility to repeat calling the function up to 5 times if an exception is thrown
    try:
        return await function(*args, **kwargs)
    except (
        tidalapi.exceptions.TooManyRequests,
        requests.exceptions.RequestException,
        spotipy.exceptions.SpotifyException,
    ) as e:
        if remaining:
            print(f"> {str(e)} occurred, retrying {remaining} times")
        else:
            print(f"> {str(e)} could not be recovered")

        if (
            isinstance(e, requests.exceptions.RequestException)
            and not e.response is None
        ):
            print(f"> response message: {e.response.text}")
            print(f"> response headers: {e.response.headers}")

        if not remaining:
            print("> aborting sync")
            print(f"> the following arguments were provided\n\n {str(args)}")
            print(traceback.format_exc())
            sys.exit(1)
        # sleep variable length of time depending on retry number
        sleep_schedule = {5: 1, 4: 10, 3: 60, 2: 5 * 60, 1: 10 * 60}
        time.sleep(sleep_schedule.get(remaining, 1))
        return await repeat_on_request_error(
            function, *args, remaining=remaining - 1, **kwargs
        )
