# Prompting Method: 
To avoid the token limits or the model finishing a script early for long speeches, I
submitted turn requests in chunks of about 5-13 turns. Each iteration I would add the already requested
prompt to the input for context and then get the next iteration output from OpenAI. It would continue until
the desired turn length was reached.

# Design Choices
- I chose to include both individual and global volumes/pause in personas.json as well to allow you to modify both the speakers and studio
as if it were a real podcast. 
- I prompt GPT to give me the json formatting immediately for the turns, which makes processing much easier but maybe wastes afew `{} and :` tokens
in the output. Not a big deal because the prompting method is in chunks.