import instruct_qa

from instruct_qa.collections.utils import load_collection
from instruct_qa.retrieval.utils import load_retriever, load_index
from instruct_qa.prompt.utils import load_template
from instruct_qa.generation.utils import load_model
from instruct_qa.response_runner import ResponseRunner

import pandas as pd

import string
import time
from importlib import reload

timings={}
timings["started load_model"] = time.time()
model = load_model("flan-t5-xxl", timings = timings)
timings["started load_collection"] = time.time()
collection = load_collection("dpr_wiki_collection")
timings["started load_index"] = time.time()
index = load_index("dpr-nq-multi-hnsw")
timings["started load_retriever"] = time.time()
retriever = load_retriever("facebook-dpr-question_encoder-multiset-base", index)
timings["started load_template"] = time.time()
prompt_template = load_template("qa")
timings["ram all loaded"] = time.time()

print(timings)

megaq = [
    ["what is haleys comet?"],
    ["what is the plot of hamlet?"],
    ["what does 'nemo videbunt' mean in latin?"]
]

megaqueries = pd.read_csv('/mnt/nfs/shared/mmlu/test/logical_fallacies_test.csv', names=['question', 'a', 'b', 'c', 'd', 'correct'])


while True:
    try:
        input("Ready to launch, please hit ENTER")
        reload(instruct_qa)
        from instruct_qa.response_runner import ResponseRunner
        timings = {}
        t1 = time.time()

        for queries in range(1):
            queries_df = megaqueries.iloc[:25]
            queries = [str(x) for x in queries_df.apply(lambda x: f'Answer the following question: {x.question} The possible answers are : A) {x.a}; B) {x.b}; C) {x.c}; D) {x.d}. No further questions allowed. Please answer only using one of the letters A, B, C, or D. Your answer:', axis=1)]
            
            runner = ResponseRunner(
                model=model,
                retriever=retriever,
                document_collection=collection,
                prompt_template=prompt_template,
                queries=queries,
                timings=timings
            )

            responses = runner()
            print(list(zip([r["response"][:5] for r in responses], list(queries_df.correct))))
            print("")
            print("elasped time", str(time.time() - t1))
    except Exception as e:
        print("attempt failed", e)
