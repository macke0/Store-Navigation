# ICA_ai
An ai that helps people find items in food stores.

Problem:
People are looking for items in food stores and can't find them. This will lead to them either seeking help from employees or leaving the store without buying the item. This leads to a bad customer experience and lost sales for the store. The stores want to sell the items and the customers want to buy them. Although since they can't find the items, there's a gap that has been formed.

Solution:
This project aims to bridge that gap by making it easier for people to shop in food stores. By using AI to identify items in the store, we can help customers find what they are looking for quickly and easily. 

Solution in depth:
We use a combination of computer vision and natural language processing to identify items in the store. We use CLIP to identify the item visually and Qwen to identify the item textually. We then use a combination of the two to identify the item. But to make it more accurate we use the stores product database to look up the item and find the most accurate match. The text recognition is done using Qwen2.5-VL-32B-Instruct-AWQ, which is a large language model that is trained on a massive dataset of text and images. 


