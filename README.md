# PDF Summarizer (RAG-based Document Q&A)

I built a PDF summarization + Q&A app that lets me ingest PDF documents, index them in a vector database, and ask questions that are answered using only the most relevant retrieved sections from the PDFs. The app uses a simple Streamlit interface on top of a FastAPI backend and a Qdrant vector store.

---

## 🚀 Features

- **PDF ingestion**
  - Reads PDFs and splits them into chunked passages
  - Generates embeddings for each chunk
  - Stores vectors + metadata (source + text) in **Qdrant**

- **Document Q&A**
  - Embeds a user question
  - Retrieves top-k relevant chunks from Qdrant
  - Generates a concise answer grounded in retrieved context
  - Returns **sources** used for the response

- **Workflow-friendly backend**
  - Ingestion and query flows are structured into steps for reliability and easier debugging.

---

##  Streamlit Portal

> Add a screenshot of the Streamlit portal here:

![Streamlit UI Screenshot](./assets/streamlit-ui.png)

*(Create an `assets/` folder and place your screenshot as `streamlit-ui.png`.)*

---

## 🧱 Tech Stack

- **Streamlit** (frontend UI)
- **FastAPI** (backend API)
- **Qdrant** (vector database) - Local Docker Container 
- **OpenAI API** (embeddings + LLM)
- **LlamaIndex** (PDF loading + chunking)

---

## 📁 Project Structure

```text
PDF-Summarizer/
  app/
    main.py              # FastAPI app + ingestion/query flows
    data_loader.py       # PDF loader, chunker, embeddings
    vector_db.py         # Qdrant storage (upsert + search/query)
    custom_types.py      # Pydantic models (step IO types)
  streamlit_app.py       # Streamlit UI
  .env                   # local environment variables (not committed)
  requirements.txt
