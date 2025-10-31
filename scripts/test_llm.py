from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:50002/v1",
    api_key="empty",
)


response = client.chat.completions.create(
    model="ui-tars",
    messages=[
        {"role": "user", "content": "Hello!"}
    ]
)

print(response.choices[0].message.content)
