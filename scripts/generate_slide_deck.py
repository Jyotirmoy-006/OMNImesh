"""
Script to generate the complete 12-slide Academic Whitepaper presentation deck
for the University Faculty Evaluation Panel.
Strict adherence to:
- 16:9 1920x1080 viewBox
- Pure flat white (#FFFFFF) background
- Dark Charcoal (#1A1A1A) text
- Deep Corporate Blue (#004080) and Emerald Green (#006633) accents only
- Zero glowing neon, zero drop shadows, zero gradients, zero 3D effects
- Titles: Minimum 56pt (60px)
- Bullet points: Minimum 32pt (34px)
- 7x7 rule: Max 7 bullets, Max 7 words per bullet
"""

import os
import html

SLIDES_DATA = [
    {
        "num": 1,
        "tag": "PROJECT INTRODUCTION",
        "title": "OMNI-MESH: Smart Traffic & Security",
        "subtitle": "B.Tech CSE AI, Term I Project",
        "bullets": [
            "University of Engineering & Management, Newtown",
            "Presented by: Jyotirmoy Santra & Team"
        ],
        "is_cover": True,
        "accent": "#004080"
    },
    {
        "num": 2,
        "tag": "PROBLEM IDENTIFICATION",
        "title": "The Problem",
        "subtitle": "Critical Weaknesses in Modern Urban Traffic Infrastructure",
        "bullets": [
            "Current systems rely on central servers.",
            "Cloud failures cause massive city traffic jams.",
            "Current systems are very expensive to install.",
            "Emergency vehicles get stuck in regular traffic.",
            "Security relies on slow manual human updates.",
            "Traffic and security are not linked together."
        ],
        "is_cover": False,
        "accent": "#004080"
    },
    {
        "num": 3,
        "tag": "MARKET ANALYSIS",
        "title": "Current Solutions",
        "subtitle": "Where Existing Commercial Solutions Fall Short",
        "bullets": [
            "Legacy systems are expensive and lack security.",
            "Existing AI models only focus on traffic.",
            "Human-operated cameras cannot control traffic lights.",
            "No system clears paths for emergencies automatically.",
            "No system runs safely without the cloud."
        ],
        "is_cover": False,
        "accent": "#004080"
    },
    {
        "num": 4,
        "tag": "RESEARCH GAP",
        "title": "The Missing Link",
        "subtitle": "Core Technical Capabilities Missing in Today's Cities",
        "bullets": [
            "No system runs locally at the intersection.",
            "Emergency vehicles need a clear path instantly.",
            "Security threats require immediate physical roadblocks.",
            "We need a system that does both.",
            "It must run on affordable, basic hardware."
        ],
        "is_cover": False,
        "accent": "#004080"
    },
    {
        "num": 5,
        "tag": "PROJECT OVERVIEW",
        "title": "Our Solution: Omni-Mesh",
        "subtitle": "A Decentralized, Dual-Objective Traffic Management Platform",
        "bullets": [
            "Creates instant green lights for emergency vehicles.",
            "Automatically traps flagged security threat vehicles.",
            "Smart AI runs directly at the intersection.",
            "Never relies on a single central server.",
            "Built-in failsafe prevents total network crashes."
        ],
        "is_cover": False,
        "accent": "#006633"
    },
    {
        "num": 6,
        "tag": "SYSTEM ARCHITECTURE",
        "title": "How It Works",
        "subtitle": "Decentralized Two-Tier City-Wide Coordination",
        "bullets": [
            "Two main parts working seamlessly together.",
            "Tier 2: City-wide brain monitors the area.",
            "Tier 1: Smart intersections control the lights.",
            "Intersections talk directly to each other.",
            "Uses extremely fast, lightweight communication messages.",
            "No central cloud required to operate safely."
        ],
        "is_cover": False,
        "accent": "#004080"
    },
    {
        "num": 7,
        "tag": "TIER 1 ARCHITECTURE",
        "title": "The Smart Intersections",
        "subtitle": "Local Artificial Intelligence Running at the Edge",
        "bullets": [
            "Cameras detect waiting traffic in real-time.",
            "Fast AI decides when to change lights.",
            "Runs smoothly on basic, affordable hardware.",
            "Processes information instantly without freezing up.",
            "Exchanges updates with neighboring intersections constantly.",
            "Reacts to changes in under a second."
        ],
        "is_cover": False,
        "accent": "#004080"
    },
    {
        "num": 8,
        "tag": "TIER 2 ARCHITECTURE",
        "title": "The Global Watchdog",
        "subtitle": "Regional Coordination with Mandatory Human Oversight",
        "bullets": [
            "Scans for security alerts across the city.",
            "Requires two cameras to verify a match.",
            "Double-checking prevents false positive alarms.",
            "Calculates the best way to trap vehicles.",
            "System pauses for a human safety check.",
            "Waits for human dispatcher to approve action."
        ],
        "is_cover": False,
        "accent": "#006633"
    },
    {
        "num": 9,
        "tag": "RELIABILITY & RESILIENCE",
        "title": "The Failsafe System",
        "subtitle": "Zero Single Point of Failure (ZSPF) Architecture",
        "bullets": [
            "Prevents the system from breaking down completely.",
            "Mode 0: Everything is connected and perfect.",
            "Mode 1: Intersections talk only to neighbors.",
            "Mode 2: Intersections work completely alone safely.",
            "Safely handles catastrophic network or power crashes.",
            "Traffic keeps flowing no matter what breaks."
        ],
        "is_cover": False,
        "accent": "#004080"
    },
    {
        "num": 10,
        "tag": "INTELLIGENT DECISION MAKING",
        "title": "Training the AI",
        "subtitle": "Balanced Multi-Objective Goal Optimization",
        "bullets": [
            "The AI learns to balance two goals.",
            "Goal 1: Keep normal traffic moving fast.",
            "Goal 2: Stop flagged vehicles immediately.",
            "System switches priorities when threats appear.",
            "This prevents the AI from getting confused.",
            "Ensures absolute safety and maximum efficiency."
        ],
        "is_cover": False,
        "accent": "#004080"
    },
    {
        "num": 11,
        "tag": "EXPERIMENTAL RESULTS",
        "title": "Next Steps & Testing",
        "subtitle": "Rigorous Simulation Benchmarks and Future Milestones",
        "bullets": [
            "Target: 100% success in stopping security threats.",
            "Target: Better traffic flow than standard systems.",
            "Testing using a realistic virtual city simulator.",
            "Adding random errors to test system strength.",
            "Preparing for physical hardware testing very soon."
        ],
        "is_cover": False,
        "accent": "#006633"
    },
    {
        "num": 12,
        "tag": "PROJECT CONCLUSION",
        "title": "Conclusion",
        "subtitle": "Key Takeaways & Open Discussion",
        "bullets": [
            "Combines smooth traffic with smart city security.",
            "Built to be affordable and highly reliable.",
            "Thank you for your time.",
            "We welcome your questions."
        ],
        "is_cover": True,
        "accent": "#004080"
    }
]

def render_slide_svg(slide):
    num = slide["num"]
    num_str = f"{num:02d}"
    tag = html.escape(slide["tag"])
    title = html.escape(slide["title"])
    subtitle = html.escape(slide["subtitle"])
    accent = slide["accent"]
    bullets = [html.escape(b) for b in slide["bullets"]]
    is_cover = slide.get("is_cover", False)

    # Calculate vertical positions
    # Top frame
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080" width="1920" height="1080">
  <!-- Pure White Background -->
  <rect width="1920" height="1080" fill="#FFFFFF" />

  <!-- Outer Academic Frame -->
  <rect x="30" y="30" width="1860" height="1020" fill="none" stroke="#CBD5E1" stroke-width="2" rx="10" />

  <!-- Top Category Badge & Slide Index -->
  <g id="slide-top-bar">
    <rect x="80" y="65" width="280" height="38" rx="6" fill="{accent}" />
    <text x="220" y="89" text-anchor="middle" font-family="'Inter', sans-serif" font-size="16" font-weight="700" fill="#FFFFFF" letter-spacing="1.5">
      {tag}
    </text>

    <rect x="1660" y="65" width="180" height="38" rx="6" fill="#F1F5F9" stroke="#CBD5E1" stroke-width="1.5" />
    <text x="1750" y="89" text-anchor="middle" font-family="'Inter', sans-serif" font-size="16" font-weight="800" fill="{accent}">
      SLIDE {num_str} / 12
    </text>
  </g>
"""

    if is_cover and num == 1:
        # Cover slide layout
        svg += f"""
  <!-- Cover Title Section (Massive Fonts) -->
  <g id="cover-header">
    <text x="960" y="300" text-anchor="middle" font-family="'Inter', sans-serif" font-size="64" font-weight="800" fill="{accent}" letter-spacing="-1">
      {title}
    </text>
    <text x="960" y="375" text-anchor="middle" font-family="'Inter', sans-serif" font-size="34" font-weight="600" fill="#006633">
      {subtitle}
    </text>
    <line x1="260" y1="430" x2="1660" y2="430" stroke="#CBD5E1" stroke-width="2.5" />
  </g>

  <!-- Presentation Metadata Card -->
  <g id="cover-metadata" transform="translate(360, 480)">
    <rect x="0" y="0" width="1200" height="340" rx="16" fill="#F8FAFC" stroke="{accent}" stroke-width="2" />
    
    <circle cx="100" cy="110" r="10" fill="{accent}" />
    <text x="130" y="120" font-family="'Inter', sans-serif" font-size="36" font-weight="700" fill="#1A1A1A">
      {bullets[0]}
    </text>

    <circle cx="100" cy="220" r="10" fill="#006633" />
    <text x="130" y="230" font-family="'Inter', sans-serif" font-size="36" font-weight="700" fill="#1A1A1A">
      {bullets[1]}
    </text>
  </g>
"""
    elif is_cover and num == 12:
        # Conclusion slide layout
        svg += f"""
  <!-- Header Section -->
  <g id="slide-header">
    <text x="80" y="180" font-family="'Inter', sans-serif" font-size="60" font-weight="800" fill="{accent}" letter-spacing="-0.5">
      {title}
    </text>
    <text x="80" y="230" font-family="'Inter', sans-serif" font-size="28" font-weight="600" fill="#4A5568">
      {subtitle}
    </text>
    <line x1="80" y1="265" x2="1840" y2="265" stroke="#CBD5E1" stroke-width="2" />
  </g>

  <!-- Bullets Box -->
  <g id="slide-content" transform="translate(80, 320)">
    <rect x="0" y="0" width="1760" height="560" rx="16" fill="#F8FAFC" stroke="{accent}" stroke-width="2" />
"""
        y_pos = 110
        for i, b in enumerate(bullets):
            color = accent if i < 2 else "#006633"
            svg += f"""
    <!-- Bullet {i+1} -->
    <g transform="translate(80, {y_pos})">
      <circle cx="16" cy="0" r="10" fill="{color}" />
      <text x="45" y="11" font-family="'Inter', sans-serif" font-size="36" font-weight="700" fill="#1A1A1A">
        {b}
      </text>
    </g>
"""
            y_pos += 115
        svg += "  </g>\n"
    else:
        # Standard Slide with 5-6 bullets
        svg += f"""
  <!-- Header Section (Min 56pt = 60px) -->
  <g id="slide-header">
    <text x="80" y="180" font-family="'Inter', sans-serif" font-size="60" font-weight="800" fill="{accent}" letter-spacing="-0.5">
      {title}
    </text>
    <text x="80" y="230" font-family="'Inter', sans-serif" font-size="28" font-weight="600" fill="#4A5568">
      {subtitle}
    </text>
    <line x1="80" y1="265" x2="1840" y2="265" stroke="#CBD5E1" stroke-width="2" />
  </g>

  <!-- Content Container Card -->
  <g id="slide-content" transform="translate(80, 310)">
    <rect x="0" y="0" width="1760" height="580" rx="16" fill="#F8FAFC" stroke="{accent}" stroke-width="2" />
"""
        # Distribute bullets evenly
        num_bullets = len(bullets)
        spacing = 500 / max(num_bullets, 1)
        y_start = 65

        for i, b in enumerate(bullets):
            cur_y = int(y_start + i * spacing)
            svg += f"""
    <!-- Bullet {i+1} -->
    <g transform="translate(70, {cur_y})">
      <circle cx="12" cy="0" r="9" fill="{accent}" />
      <text x="40" y="11" font-family="'Inter', sans-serif" font-size="34" font-weight="700" fill="#1A1A1A">
        {b}
      </text>
    </g>
"""
        svg += "  </g>\n"

    # Bottom academic footer bar
    svg += f"""
  <!-- Bottom Academic Footer Bar -->
  <g id="slide-footer">
    <line x1="80" y1="995" x2="1840" y2="995" stroke="#CBD5E1" stroke-width="1.5" />
    <text x="80" y="1025" font-family="'Inter', sans-serif" font-size="16" font-weight="700" fill="{accent}">
      OMNI-MESH: Smart Traffic &amp; Security
    </text>
    <text x="960" y="1025" text-anchor="middle" font-family="'Inter', sans-serif" font-size="16" font-weight="600" fill="#64748B">
      B.Tech CSE AI Term I Evaluation • University of Engineering &amp; Management, Newtown
    </text>
    <text x="1840" y="1025" text-anchor="end" font-family="'Inter', sans-serif" font-size="16" font-weight="700" fill="#006633">
      Academic Whitepaper Light Theme
    </text>
  </g>
</svg>
"""
    return svg

def main():
    output_dir = os.path.join("docs", "slides")
    os.makedirs(output_dir, exist_ok=True)

    for slide in SLIDES_DATA:
        filename = f"slide_{slide['num']:02d}.svg"
        path = os.path.join(output_dir, filename)
        content = render_slide_svg(slide)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Generated: {path}")

    print("All 12 SVG slides generated successfully!")

if __name__ == "__main__":
    main()
