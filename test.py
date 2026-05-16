from google import genai

client = genai.Client(api_key="AIzaSyDo6WTMNGPntGS-EyVp44WZJHqd8ZONW4I")

for model in client.models.list():
    print(model.name)