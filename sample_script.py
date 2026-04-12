"""
sample_script.py — A deliberately imperfect Python script for testing the Code Review Agent.
Contains several style issues, complexity smells, and missing docstrings on purpose.
"""

import os, sys, json
from typing import List

API_KEY = "hardcoded-secret-key-12345"   # intentional secret smell

class DataProcessor:
    def __init__(self,data,threshold):
        self.data=data
        self.threshold=threshold
        self.results=[]

    def process(self):
        for item in self.data:
            if item>0:
                if item>self.threshold:
                    if item%2==0:
                        self.results.append(item*2)
                    else:
                        self.results.append(item*3)
                else:
                    self.results.append(item)
            else:
                pass
        return self.results

    def save(self,path):
        with open(path,"w") as f:
            json.dump(self.results,f)


def fetch_data(url,timeout=30):
    import urllib.request
    response = urllib.request.urlopen(url,timeout=timeout)
    return response.read()


def compute_stats(numbers: List[float]):
    total = 0
    for n in numbers:
        total = total + n
    mean = total / len(numbers)  # will crash on empty list
    variance = sum((x - mean) ** 2 for x in numbers) / len(numbers)
    return {"mean": mean, "variance": variance}


def main():
    data = [1,-2,3,4,-5,6,7,8,9,10]
    processor = DataProcessor(data,5)
    results = processor.process()
    print("Results:", results)

    stats = compute_stats(results)
    print("Stats:", stats)

    processor.save("/tmp/output.json")


if __name__=="__main__":
    main()
