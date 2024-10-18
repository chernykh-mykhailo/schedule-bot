# Импортируем массивы из файла responses.py
from responses import responses_easy, responses_username

# Remove duplicates from the lists
responses_easy = list(set(responses_easy))
responses_username = list(set(responses_username))

# Save the updated lists back to the file
with open('responses.py', 'w') as f:
    f.write('responses_easy = [\n')
    for response in responses_easy:
        f.write('    "' + response + '",\n')
    f.write(']\n\n')
    f.write('responses_username = [\n')
    for response in responses_username:
        f.write('    "' + response + '",\n')
    f.write(']\n')