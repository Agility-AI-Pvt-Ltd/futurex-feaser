from pipeline.graph import app as main_app
from pipeline.qa_graph import qa_app
from pipeline.idea_refinement_graph import idea_refinement_app

def generate_graphs():
    # Generate Markdown documentation with Mermaid charts
    with open("architecture_diagrams.md", "w") as f:
        f.write("# FutureX Feaser Architecture\n\n")
        f.write("## 1. Main Analysis Pipeline\n\n```mermaid\n")
        f.write(main_app.get_graph().draw_mermaid())
        f.write("\n```\n\n")
        
        f.write("## 2. Q&A Pipeline\n\n```mermaid\n")
        f.write(qa_app.get_graph().draw_mermaid())
        f.write("\n```\n")

        f.write("## 3. Idea Refinement Pipeline\n\n```mermaid\n")
        f.write(idea_refinement_app.get_graph().draw_mermaid())
        f.write("\n```\n")
        
    print("Created architecture_diagrams.md")

    # Try to generate actual PNG images
    try:
        main_png = main_app.get_graph().draw_mermaid_png()
        with open("main_pipeline.png", "wb") as f:
            f.write(main_png)
            
        qa_png = qa_app.get_graph().draw_mermaid_png()
        with open("qa_pipeline.png", "wb") as f:
            f.write(qa_png)
            
        refine_png = idea_refinement_app.get_graph().draw_mermaid_png()
        with open("idea_refinement_pipeline.png", "wb") as f:
            f.write(refine_png)
            
        print("Created main_pipeline.png, qa_pipeline.png, and idea_refinement_pipeline.png")
    except Exception as e:
        print(f"PNG generation failed (this is common if httpx isn't installed or without internet): {e}")
        print("You can view the architecture graphs using the architecture_diagrams.md file instead.")

if __name__ == "__main__":
    generate_graphs()
