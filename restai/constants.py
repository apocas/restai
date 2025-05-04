from enum import Enum

class ERROR_MESSAGES(str, Enum):
    def __str__(self) -> str:
        return super().__str__()

    DEFAULT = (
        lambda err="": f'{"Something went wrong :/" if err == "" else "[ERROR: " + str(err) + "]"}'
    )
    ENV_VAR_NOT_FOUND = "Required environment variable not found. Terminating now."
    CREATE_USER_ERROR = "Oops! Something went wrong while creating your account. Please try again later. If the issue persists, contact support for assistance."
    DELETE_USER_ERROR = "Oops! Something went wrong. We encountered an issue while trying to delete the user. Please give it another shot."
    EMAIL_MISMATCH = "Uh-oh! This email does not match the email your provider is registered with. Please check your email and try again."
    EMAIL_TAKEN = "Uh-oh! This email is already registered. Sign in with your existing account or choose another email to start anew."
    USERNAME_TAKEN = (
        "Uh-oh! This username is already registered. Please choose another username."
    )
    FILE_EXISTS = "Uh-oh! This file is already registered. Please choose another file."

    INVALID_TOKEN = (
        "Your session has expired or the token is invalid. Please sign in again."
    )
    INVALID_CRED = "The email or password provided is incorrect. Please check for typos and try logging in again."
    INVALID_EMAIL_FORMAT = "The email format you entered is invalid. Please double-check and make sure you're using a valid email address (e.g., yourname@example.com)."

    UNAUTHORIZED = "401 Unauthorized"
    ACCESS_PROHIBITED = "You do not have permission to access this resource. Please contact your administrator for assistance."

    FILE_NOT_SENT = "FILE_NOT_SENT"
    FILE_NOT_SUPPORTED = "Oops! It seems like the file format you're trying to upload is not supported. Please upload a file with a supported format and try again."

    NOT_FOUND = "We could not find what you're looking for :/"
    TEAM_NOT_FOUND = "The team you're looking for could not be found."
    TEAM_NAME_TAKEN = "This team name is already in use. Please choose a different name."
    NOT_TEAM_ADMIN = "You do not have administrative privileges for this team."
    NOT_TEAM_MEMBER = "You are not a member of this team."

    PANDOC_NOT_INSTALLED = "Pandoc is not installed on the server. Please contact your administrator for assistance."
    INCORRECT_FORMAT = (
        lambda err="": f"Invalid format. Please use the correct format{err}"
    )
    RATE_LIMIT_EXCEEDED = "API rate limit exceeded"

    MODEL_NOT_FOUND = lambda name="": f"Model '{name}' was not found"
    OPENAI_NOT_FOUND = lambda name="": "OpenAI API was not found"
    CREATE_API_KEY_ERROR = "Oops! Something went wrong while creating your API key. Please try again later. If the issue persists, contact support for assistance."
    API_KEY_CREATION_NOT_ALLOWED = "API key creation is not allowed in the environment."

    EMPTY_CONTENT = "The content provided is empty. Please ensure that there is text or data present before proceeding."

    INVALID_URL = (
        "Oops! The URL you provided is invalid. Please double-check and try again."
    )

    FILE_TOO_LARGE = (
        lambda size="": f"Oops! The file you're trying to upload is too large. Please upload a file that is less than {size}."
    )

    DUPLICATE_CONTENT = (
        "Duplicate content detected. Please provide unique content to proceed."
    )
    FILE_NOT_PROCESSED = "Extracted content is not available for this file. Please ensure that the file is processed before proceeding."
