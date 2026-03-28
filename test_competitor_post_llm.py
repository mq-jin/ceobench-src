"""Test: One ground truth boost → 3 posts with independent noise (same RNG as production)."""

from numpy.random import Generator, PCG64
from anthropic import AnthropicBedrock

client = AnthropicBedrock(aws_region="us-east-2")
model = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
temperature = 0.95

# --- Ground truth competitor event ---
GROUND_TRUTH_BOOST = 0.085  # moderate-range event
EVENT_DESCRIPTION = "A competitor launched a significant feature upgrade."
PRODUCT_NAME = "NovaMind"

# Separate noise RNG (mirrors production: seed XOR 'NOIS')
noise_rng = Generator(PCG64(42 ^ 0x4E4F4953))

# Competitor RNG for name/perspective selection (mirrors production: seed XOR 'COMP')
comp_rng = Generator(PCG64(42 ^ 0x434F4D50))

competitor_names = ['RivalTech', 'NexGen Solutions', 'CloudPeak', 'QuantumEdge', 'ApexSaaS']
perspectives = [
    'industry analyst', 'tech journalist', 'SaaS market watcher',
    'former employee of a competing company', 'venture capital analyst',
    'product review blogger', 'enterprise buyer evaluating options',
]

severity_guidance = {
    "minor": "This is a small, incremental improvement. Tone: measured, noting it but not alarmed.",
    "moderate": "This is a meaningful upgrade that raises the bar. Tone: impressed, noting competitive pressure.",
    "major": "This is a significant product overhaul. Tone: urgent, this changes market expectations.",
    "transformative": "This is a market-redefining breakthrough. Tone: alarmed/excited, everyone must respond.",
}

print(f"Ground truth boost: {GROUND_TRUTH_BOOST:.4f}")
print(f"Event: {EVENT_DESCRIPTION}")
print(f"Product: {PRODUCT_NAME}")

for i in range(3):
    # Independent noise draw per post: additive, uniform in [-0.25*boost, +0.25*boost]
    noise = float(noise_rng.uniform(-0.25, 0.25)) * GROUND_TRUTH_BOOST
    noisy_boost = max(0.0, GROUND_TRUTH_BOOST + noise)

    # Classify severity from noisy boost
    if noisy_boost < 0.03:
        severity = 'minor'
    elif noisy_boost < 0.10:
        severity = 'moderate'
    elif noisy_boost < 0.20:
        severity = 'major'
    else:
        severity = 'transformative'

    # Pick competitor name and perspective
    competitor_name = competitor_names[int(comp_rng.integers(0, len(competitor_names)))]
    perspective = perspectives[int(comp_rng.integers(0, len(perspectives)))]

    system_prompt = f"""You are a {perspective} posting on social media about a competitor product launch in the SaaS/AI tools market.

Competitor: {competitor_name}
Event: {EVENT_DESCRIPTION}
Your perceived quality boost: {noisy_boost:.4f}
Severity level: {severity}

{severity_guidance[severity]}

This number ({noisy_boost:.4f}) is YOUR subjective perception of how much the competitor improved — based on your personal experience testing the product, reading early reviews, or talking to beta users. Different observers may perceive the improvement differently. You believe it to be a {noisy_boost:.4f} quality boost based on what you've seen.

Context: {PRODUCT_NAME} is an existing player in this space. The competitor's improvement puts pressure on {PRODUCT_NAME} and similar tools.

Guidelines:
- Write a single, authentic social media post (1-3 sentences, under 100 words)
- You MUST explicitly mention the quality boost number ({noisy_boost:.4f}) somewhere in your post, framed as your own estimate or perception — e.g. "from what I've seen, about a {noisy_boost:.4f} quality boost" or "I'd estimate a {noisy_boost:.4f} improvement" or "my testing suggests a {noisy_boost:.4f} bump"
- Calibrate your reaction to the magnitude: {noisy_boost:.4f} is {'barely noticeable' if noisy_boost < 0.03 else 'notable' if noisy_boost < 0.10 else 'very significant' if noisy_boost < 0.20 else 'massive and market-changing'}
- Vary your style — sometimes use hashtags, sometimes don't; sometimes tag companies, sometimes don't
- Sound like a real person, not a press release
- Output ONLY the post text, nothing else."""

    user_prompt = f"Write a social media post reacting to {competitor_name}'s product launch."

    print(f"\n{'='*60}")
    print(f"POST {i+1}: noise={noise:+.4f} → noisy_boost={noisy_boost:.4f} ({severity})")
    print(f"  competitor={competitor_name}, perspective={perspective}")
    print(f"{'='*60}")
    print(f"\n--- PROMPT (system) ---")
    print(system_prompt)
    print(f"\n--- PROMPT (user) ---")
    print(user_prompt)

    response = client.messages.create(
        model=model,
        max_tokens=200,
        temperature=temperature,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    post_text = response.content[0].text.strip()
    print(f"\n--- GENERATED POST ---")
    print(post_text)
    print(f"\n(tokens: {response.usage.input_tokens} in, {response.usage.output_tokens} out)")
