clip_sok.py: 
    We take each image of products in the store, converts it to a 512 dimensional vector. Then wehen the user uploads an image, we convert that image to a 512 dimensional vector as well. We compare them by taking the dot product between the vectors. Dimension 1 x 1, 2 x 2 and so on. If the images are similar then the dot product will be closer to 1. If the images are not similar then the dot product will be closer to 0, called cosine similarity.

