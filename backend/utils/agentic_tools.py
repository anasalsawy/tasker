from langchain_community.document_loaders import UnstructuredPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import WebBaseLoader, YoutubeLoader
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import AzureChatOpenAI


llm = AzureChatOpenAI(
    azure_deployment='gpt-4.1-mini',
    api_version='2024-12-01-preview',
    temperature=0.3,
    max_tokens=None,
    timeout=None,
    max_retries=2,
)


def fetch_and_summarize_url(url: str) -> str:
    loader = WebBaseLoader(url)
    documents = loader.load()

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    docs = text_splitter.split_documents(documents)

    full_text = "\n\n".join(doc.page_content for doc in docs)

    prompt = ChatPromptTemplate.from_template("Summarize the following:\n\n{input}")
    chain = prompt | llm

    result = chain.invoke({"input": full_text})
    return result.content if hasattr(result, "content") else str(result)


def fetch_and_summarize_pdf(file_path: str = None, url: str = None) -> str:
    if url:
        import requests
        import tempfile
        response = requests.get(url)
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        temp_file.write(response.content)
        temp_file.close()
        file_path = temp_file.name

    loader = UnstructuredPDFLoader(file_path)
    documents = loader.load()

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    docs = text_splitter.split_documents(documents)

    # Prepare the full text
    full_text = "\n\n".join(doc.page_content for doc in docs)

    prompt = ChatPromptTemplate.from_template("Summarize the following:\n\n{input}")
    chain = prompt | llm

    result = chain.invoke({"input": full_text})
    return result.content if hasattr(result, "content") else str(result)


def summarize_youtube_video(url: str) -> str:
    try:
        loader = YoutubeLoader.from_youtube_url(url, add_video_info=False)
        documents = loader.load()
    except Exception as e:
        return f"Unexpected error fetching video transcript: {str(e)}"

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    docs = text_splitter.split_documents(documents)

    # Prepare the full text
    full_text = "\n\n".join(doc.page_content for doc in docs)

    prompt = ChatPromptTemplate.from_template("Summarize the following:\n\n{input}")
    chain = prompt | llm

    result = chain.invoke({"input": full_text})
    return result.content if hasattr(result, "content") else str(result)


def run_tool_server_side(tool_name: str, args: dict) -> str:
    if tool_name == "fetch_url":
        return fetch_and_summarize_url(args["url"])

    if tool_name == "read_pdf":
        return fetch_and_summarize_pdf(args.get("file_path"), args.get("url"))

    if tool_name == "summarize_youtube_video":
        return summarize_youtube_video(args["url"])

    raise ValueError(f"Unsupported tool: {tool_name}")