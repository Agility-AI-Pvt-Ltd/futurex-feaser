import os
import sys

# Add the 'backend' directory to the python path so we can import from pipeline
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(backend_dir)

from pipeline.graph import app

def export_graph_image():
    print("Generating graph image from LangGraph pipeline...")
    
    try:
        # Get the serialized mermaid PNG data
        png_data = app.get_graph().draw_mermaid_png()
        
        # Save it to the sandbox folder
        output_path = os.path.join(os.path.dirname(__file__), "langgraph_flow.png")
        with open(output_path, "wb") as f:
            f.write(png_data)
            
        print(f"✅ Successfully saved LangGraph architecture to: {output_path}")
        
    except Exception as e:
        print("❌ Failed to generate graph. Note: You may need to install Mermaid dependencies.")
        print(e)
        
        # Fallback to pure Mermaid markdown
        print("\nFallback: Saving raw Mermaid markdown instead...")
        mermaid_md = app.get_graph().draw_mermaid()
        md_output_path = os.path.join(os.path.dirname(__file__), "langgraph_flow.md")
        with open(md_output_path, "w") as f:
            f.write(mermaid_md)
        print(f"✅ Saved mermaid markdown to: {md_output_path}")


if __name__ == "__main__":
    export_graph_image()
