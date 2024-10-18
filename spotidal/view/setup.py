from InquirerPy import prompt

def get_credentials():
    print("Spotify credentials not found. Let's set them up.")

    questions = [
        {
            "type": "input",
            "name": "username",
            "message": "Enter your Spotify username:",
        },
        {
            "type": "input",
            "name": "client_id",
            "message": "Spotify client id:",
        },
        {
            "type": "input",
            "name": "client_secret",
            "message": "Spotify client secret:",
        },
    ]

    credentials = prompt(questions)
    return credentials