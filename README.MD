# Shoestring AWS Relay
This is a Shoestring Data Output Service Module which relay's MQTT messages from a local MQTT broker to AWS's IoT Core.
# Configuration
The relay is configured in the `config.toml` file at `./aws_relay/config`. There is configuration documentation at the top of the file.
For more detailed assistance and support join the [Shoestring Community](https://comunity.digitalshoestring.net) and view the guide [here](https://community.digitalshoestring.net/t/use-shoestring-aws-relay-for-uploading-shoestring-solution-data-to-mdep/47) or ask questions.

Place the IoT core certificates at `./aws_relay/certs/`

# How to Run
This service module is set up to run using docker and docker compose. Install both by following their respective guides, then download this code using the latest release (On the right of the page if you're viewing this on Github) and run `docker compose build` followed by `./start.sh` on the command line in the location where the files have been saved.