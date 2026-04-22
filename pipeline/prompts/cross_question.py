def get_cross_question_prompt(idea: str, problem_solved: str, ideal_customer: str, history_str: str, current_message: str, previous_analysis: str = "") -> str:
    """
    Generates the prompt used to ask a clarifying cross-question to the user.
    """
    analysis_block = f"Previous Feasibility Analysis Results:\n{previous_analysis}\n\n" if previous_analysis.strip() else ""
    
    return (
        f"You are an AI validating a startup idea.\n"
        f"Original Startup Idea: {idea}\n"
        f"Problem to solve: {problem_solved}\n"
        f"Ideal Customer: {ideal_customer}\n\n"
        f"{analysis_block}"
        f"Conversation History so far:\n{history_str}\n\n"
        f"User's Latest Reply: {current_message}\n\n"
        "Based on all of the above context, ask exactly ONE critical clarifying question to better understand their market approach or to dig deeper into any missing details."
    )
