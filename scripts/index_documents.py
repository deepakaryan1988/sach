#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.pipeline.faiss_manager import FAISSIndexManager


SAMPLE_DOCUMENTS = [
    {
        "id": "1",
        "title": "NASA Confirms Earth is Round",
        "content": "NASA confirms that Earth is an oblate spheroid, approximately 7,926 miles in diameter at the equator. This has been verified through satellite imagery, space travel, and physics.",
    },
    {
        "id": "2",
        "title": "Global Temperature Rise",
        "content": "According to NOAA and NASA, global average temperature has risen by approximately 1.1°C since pre-industrial times. 2023 was one of the warmest years on record.",
    },
    {
        "id": "3",
        "title": "Vaccine Safety Studies",
        "content": "Extensive studies published in peer-reviewed journals including NEJM, Lancet, and JAMA confirm that vaccines are safe and effective for preventing disease.",
    },
    {
        "id": "4",
        "title": "Moon Landing Facts",
        "content": "The Apollo 11 moon landing occurred on July 20, 1969. Multiple independent sources, including Soviet tracking stations, confirm the missions took place.",
    },
    {
        "id": "5",
        "title": "Evolution Scientific Consensus",
        "content": "The theory of evolution by natural selection is supported by extensive evidence from genetics, paleontology, and comparative anatomy. Over 95% of scientists accept evolution as fact.",
    },
    {
        "id": "6",
        "title": "COVID-19 Origin Studies",
        "content": "Studies in Nature and Science journals suggest COVID-19 likely originated from natural spillover, though the exact origin remains under scientific investigation.",
    },
    {
        "id": "7",
        "title": "Renewable Energy Growth",
        "content": "IRENA reports that renewable energy capacity has grown by 50% in the last decade, with solar leading the growth at 22% annual average.",
    },
    {
        "id": "8",
        "title": "Water on Mars",
        "content": "NASA's Mars rover missions have confirmed the presence of water ice on Mars. The planet had liquid water on its surface approximately 3 billion years ago.",
    },
]


def load_documents_from_file(file_path: str) -> list:
    with open(file_path, "r") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(
        description="Index documents for TruthLens retrieval"
    )
    parser.add_argument("--documents", "-d", help="Path to JSON file with documents")
    parser.add_argument(
        "--list", "-l", action="store_true", help="List sample documents"
    )
    args = parser.parse_args()

    if args.list:
        print("Sample documents:")
        for doc in SAMPLE_DOCUMENTS:
            print(f"  [{doc['id']}] {doc['title']}")
        return

    documents = SAMPLE_DOCUMENTS
    if args.documents:
        documents = load_documents_from_file(args.documents)

    print(f"Indexing {len(documents)} documents...")
    manager = FAISSIndexManager()
    manager.build_index(documents)
    print(f"Index built successfully with {manager.index.ntotal} vectors")


if __name__ == "__main__":
    main()
