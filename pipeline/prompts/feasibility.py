def get_feasibility_prompt(idea: str, ideal_customer: str, search_results: str) -> str:
    return (
        f"Analyze feasibility of '{idea}' for '{ideal_customer}'.\n\n"
        f"We have scraped live data from TWO sources:\n"
        f"  1. General web search — market reports, news, and competitor sites.\n"
        f"  2. Reddit community discussions — real user opinions, pain points, and demand signals.\n\n"
        f"=== SCRAPED WEB DATA (General + Reddit) ===\n"
        f"{search_results}\n"
        f"==========================================\n\n"
        "Provide the response as a single valid JSON object with EXACTLY these 7 keys:\n"
        '{\n'
        '  "chain_of_thought": [\n'
        '    "Step 1: Extract explicitly stated facts from general web sources about the current market.",\n'
        '    "Step 2: Extract user pain points, demand signals, and opinions from Reddit discussions.",\n'
        '    "Step 3: Identify exact competitor strengths and weaknesses from the data.",\n'
        '    "Step 4: Determine if the proposed idea fills a genuine gap validated by both market data and community sentiment.",\n'
        '    "Step 5: Synthesize all findings to determine the overall feasibility and score."\n'
        '  ],\n'
        '  "idea_fit": "Analyze how well this idea solves the target problem, referencing both market data and Reddit sentiment...",\n'
        '  "competitors": "List and analyze the specific competitors found in the web data...",\n'
        '  "opportunity": "Identify specific market gaps or opportunities mentioned in formal sources AND validated by Reddit community discussions...",\n'
        '  "score": "Give a feasibility score out of 100 based on the full analysis (e.g. 75/100)...",\n'
        '  "targeting": "Recommend exact customer segments to target based on the research and community insights...",\n'
        '  "next_step": "Provide actionable next steps to validate or build the product..."\n'
        '}\n\n'
        "Do not include any markdown formatting like ```json, just return the raw valid JSON object. "
        "Your entire analysis MUST be grounded in the provided web data. "
        "Where relevant, explicitly note whether a finding comes from formal market data or Reddit community discussions."
    )

