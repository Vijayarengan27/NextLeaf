
import json
import os

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.environ["META_API_KEY"],
    base_url="https://api.meta.ai/v1",
)

MODEL = "muse-spark-1.3"

TRAITS = {
    "emotional_intensity": "0 = emotionally restrained, 1 = emotionally intense",
    "darkness": "0 = light, 1 = bleak or disturbing",
    "hope_cozy": "0 = bleak or hopeless, 1 = comforting and hopeful",
    "humour": "0 = serious, 1 = humorous",
    "tension_suspense": "0 = relaxed, 1 = suspenseful",
    "pace": "0 = slow-burn, 1 = propulsive",
    "action_violence": "0 = little action or violence, 1 = substantial",
    "romance_spice": "0 = little romance or sexual content, 1 = prominent",
    "prose_density": "0 = clean and direct, 1 = literary and dense",
    "character_depth": "0 = relatively simple, 1 = psychologically complex",
    "plot_complexity": "0 = straightforward, 1 = intricate or twisty",
    "world_immersion": "0 = minimal setting immersion, 1 = richly immersive",
    "philosophical_depth": "0 = little philosophical exploration, 1 = deep",
    "weirdness_experimental": "0 = conventional, 1 = strange or experimental",
}


def interpret_query(query: str) -> dict:
    """Convert a reader's request into retrieval signals and trait preferences."""

    trait_schema = {
        name: {
            "target": None,
            "importance": 0.0,
        }
        for name in TRAITS
    }

    prompt = f"""
You are the query interpreter for NextLeaf, a literary book recommender.

Analyze the reader's request and return ONLY valid JSON with this schema:

{{
  "content_intent": 0.0,
  "experience_intent": 0.0,
  "trait_intent": 0.0,
  "content_query": "",
  "experience_query": "",
  "trait_preferences": {json.dumps(trait_schema)},
  "must_avoid": [],
  "reasoning": ""
}}

Definitions:
- content_intent: interest in subject matter, themes, setting, ideas,
  historical periods, relationships, or what the book explores.
- experience_intent: desired reading atmosphere, mood, emotional effect,
  prose feel, pacing experience, and emotional aftertaste.
- trait_intent: how explicitly the request expresses measurable preferences
  such as darkness, humour, pace, romance, or philosophical depth.
- The three intent weights must be nonnegative and sum to 1.
- content_query: rewrite only the subject-matter part as a natural search query.
- experience_query: rewrite only the desired reading experience as a natural
  search query.
- If a channel is irrelevant, its query may be an empty string.
- Trait target must be a number from 0 to 1, or null.
- Trait importance must be between 0 and 1.
- Use null and importance 0 for traits not expressed or strongly implied.
- Do not invent preferences. For example, melancholic does not necessarily
  mean the reader wants complex plot twists.
- Interpret trait targets according to these definitions:
{json.dumps(TRAITS, indent=2)}
- For a contradictory trait, represent the dominant preference and explain
  ambiguity briefly in reasoning.
- must_avoid contains only explicit exclusions, not general dislikes.
  These are content/safety constraints such as "no sexual violence".
  Do not treat them as ordinary preferences.
- reasoning should briefly explain the signal weights.

Reader request:
{query}
"""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Return only valid JSON. Follow the schema exactly. "
                    "Never invent unstated reader preferences."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
    )

    raw = response.choices[0].message.content
    if not raw:
        raise ValueError("Muse returned an empty response.")

    # Accommodate models that wrap JSON in Markdown fences.
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    result = json.loads(raw)

    required = {
        "content_intent",
        "experience_intent",
        "trait_intent",
        "content_query",
        "experience_query",
        "trait_preferences",
        "must_avoid",
        "reasoning",
    }
    if set(result) != required:
        raise ValueError(
            f"Unexpected interpreter keys: {set(result) ^ required}"
        )

    weights = [
        float(result["content_intent"]),
        float(result["experience_intent"]),
        float(result["trait_intent"]),
    ]

    if any(w < 0 or w > 1 for w in weights):
        raise ValueError(f"Invalid intent weights: {weights}")

    if abs(sum(weights) - 1.0) > 0.02:
        raise ValueError(f"Intent weights do not sum to 1: {weights}")

    preferences = result["trait_preferences"]
    if set(preferences) != set(TRAITS):
        raise ValueError("Muse returned the wrong set of trait keys.")

    for name, pref in preferences.items():
        target = pref["target"]
        importance = float(pref["importance"])

        if target is not None and not 0 <= float(target) <= 1:
            raise ValueError(f"Invalid target for {name}: {target}")

        if not 0 <= importance <= 1:
            raise ValueError(f"Invalid importance for {name}")

        if target is None and importance != 0:
            raise ValueError(
                f"{name}: importance must be zero when target is null."
            )

    return result


if __name__ == "__main__":
    query = input("What do you want to read? ").strip()
    interpretation = interpret_query(query)
    print(json.dumps(interpretation, indent=2, ensure_ascii=False))
