# Prompting Method: 
To avoid the token limits or the model finishing a script early for long speeches, I
submitted turn requests in chunks of about 5-13 turns. Each iteration I would add the already requested
prompt to the input for context and then get the next iteration output from OpenAI. It would continue until
the desired turn length was reached.

# Design Choices
- I chose to include both individual and global volumes/pause in personas.json as well to allow you to modify both the speakers and studio
as if it were a real podcast. 
- I prompt GPT to output the json formatting immediately for the turns. This makes processing much easier but maybe wastes a few `{} and :` tokens
in the output for json formatting. Not a big deal because the prompting method is in multiple chunks.
- The target duration is currently prompted by calculating an approximate number of short turns between the podcasters. It could be improved
by including pauses or a true speaker wpm (not average wpm) in the calculation to get closer to the input target time. 