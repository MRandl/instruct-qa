import json
import os
from pathlib import Path
import numpy as np
import requests
import re
import time

from instruct_qa.retrieval.utils import dict_values_list_to_numpy
from instruct_qa.dataset.qa import GenericQADataset
from instruct_qa.generation import ProbabilityGenerator

from tqdm import tqdm



class ResponseRunner:
    def __init__(
        self,
        model,
        retriever,
        document_collection,
        prompt_template,
        timings,
        cache,
        cache_depth,
        db_k,
        use_rag=True,
        dataset=None,
        queries=None,
        output_path=None,
        k=10,
        batch_size=1,
        logging_interval=256,
        use_hosted_retriever=False,
        hosted_retriever_url="http://10.140.16.91:42010/search",
        use_cached_retrieved_results=False,
        post_process_response=False,
    ):
        self._model = model
        self._probamodel = ProbabilityGenerator(model.model, model.tokenizer)
        self._retriever = retriever
        self._document_collection = document_collection
        self._prompt_template = prompt_template
        self.timings = timings
        self.cache = cache
        self.cache_hit = 0
        self.cache_depth = cache_depth
        self.use_rag = use_rag
        self.db_k = db_k

        # either dataset or queries should be specified, but not both
        assert (dataset is None) != (queries is None), "Either dataset or queries should be specified, but not both"
        if queries:
            dataset = GenericQADataset(queries)
        self._dataset = dataset
        self._output_path = output_path
        self._k = k
        self._batch_size = batch_size
        self._logging_interval = logging_interval
        self._use_hosted_retriever = use_hosted_retriever
        self._hosted_retriever_url = hosted_retriever_url
        self._use_cached_retrieved_results = use_cached_retrieved_results
        self._collection_name = document_collection.get_name()
        self._post_process_response = post_process_response

    def post_process_response(self, response):
        return self._model.post_process_response(response)

    def rag_call(self, batch, queries):

        t1 = time.time()
    
        if self._use_hosted_retriever:
            post_results = requests.post(
                url=self._hosted_retriever_url,
                json={
                    "queries": queries,
                    "k": self._k,
                    "dataset": self._collection_name,
                },
            )
            r_dict = dict_values_list_to_numpy(post_results.json())
            retrieved_indices = r_dict["indices"]
        elif self._use_cached_retrieved_results:
            retrieved_ctx_ids = self._retriever.retrieve(queries, k=self._k)
            retrieved_indices = [
                self._document_collection.get_indices_from_ids(x)
                for x in retrieved_ctx_ids
            ]
        else:
            encoded = self._retriever.encode_queries(queries)
            cache_res = self.cache.find(list(encoded[0]))
            if cache_res is not None:
                retrieved_indices = [cache_res]
                self.cache_hit += 1
            else:
                r_dict = self._retriever.retrieve(encoded, k=self.db_k)
                retrieved_indices = r_dict["indices"]
                self.cache.insert(list(encoded[0]), list(retrieved_indices[0]))


        # Get the document texts.
        passages = [
            self._document_collection.get_passages_from_indices(indices)
            for indices in retrieved_indices
        ]

        if self.db_k > self._k: # need to rerank
            encoded_passages = self._retriever.encode_queries(passages[0]) #(20, 768)
            encoded_query = encoded[0]
            distances = np.linalg.norm(encoded_passages - encoded_query, axis=1)
            closest_indices = np.argsort(distances)[:5]
            closest_indices_sorted = sorted(closest_indices)
            #print(closest_indices_sorted, encoded_query.shape, encoded_passages.shape, distances.shape)
            passages = [[passages[0][i] for i in list(closest_indices_sorted)]]



        prompts = [
            self._prompt_template(
                sample=sample,
                passages=p,
            )
            for sample, p in zip(batch, passages)
        ]

        return prompts, (time.time() - t1)

    def get_probas(self, k): #todo batching
        batches = [
            self._dataset[i:i+1]
            for i in range(len(self._dataset))
        ]
        ret = []
        trags = []
        for batch in batches:
            queries = self._dataset.get_queries(batch)
            if self.use_rag:
                prompts, trag = self.rag_call(batch, queries)
            else:
                prompts = [
                    self._prompt_template(
                        sample=sample,
                        passages=[{"title" : "Not Found", "text" : "No corresponding source was found."}],
                    )
                    for sample in batch
                ]
                trag = 0
                retrieved_indices = [0] * self._k

            ret.append(self._probamodel(prompts[0], k))
            trags.append(trag)
        return ret, trags

    def _write_results_to_file(self, results):
        # Use pathlib to create a folder of the output path if it is not created
        # already.
        Path(self._output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self._output_path, "a") as f:
            f.writelines(json.dumps(result) + "\n" for result in results)

    def recompute_embeddings(passages):
        return self._retriever.encode_queries(passages)

    def rerank(target, embeddings):
        print(target)
        print("-----")
        print(embeddings)
        return range(len(embeddings))
