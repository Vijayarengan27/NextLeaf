import base64
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.environ["META_API_KEY"],
    base_url="https://api.meta.ai/v1",
)

MODEL = "muse-spark-1.3"


def interpret_image(image_bytes: bytes, content_type: str) -> str:
    """
    Convert an uploaded image into a reading-mood description.
    """

    encoded_image = base64.b64encode(image_bytes).decode("utf-8")
    image_url = f"data:{content_type};base64,{encoded_image}"

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an image interpreter for NextLeaf, "
                    "an emotion-aware literary book recommender. "
                    "Analyze images for their visual atmosphere and "
                    "translate that into a reading experience."
                ),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": """
Analyze this image as inspiration for finding a book.

Describe:
- Overall emotional atmosphere and mood
- Colours, lighting and visual tone
- Setting and environment
- Themes, symbolism and implied narrative
- The kind of reading experience this image evokes

Focus on the feelings and atmosphere rather than merely
listing objects in the image.

Do not invent a specific book or author.
Do not assume the image necessarily represents the user's
current emotional state.

Return a concise, evocative description in 100-150 words.
""",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": image_url},
                    },
                ],
            },
        ],
        temperature=0.3,
    )

    result = response.choices[0].message.content

    if not result:
        raise ValueError("Muse could not interpret the uploaded image.")

    return result.strip()