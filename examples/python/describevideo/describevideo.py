import cv2
import requests
from requests.auth import HTTPBasicAuth
import base64
from cap_from_youtube import cap_from_youtube

basic = HTTPBasicAuth('demo', 'demo')

def describe_frame(frame):
    _, buffer = cv2.imencode('.jpg', frame)
    frame_base64 = base64.b64encode(buffer).decode('utf-8')
    req = requests.post('https://ai.ince.pt/projects/vision/question', auth=basic, json={"question": "Describe this image, be detailed.", "image": frame_base64, "lite": True}, timeout=190)
    output = req.json()
    return output["answer"]

def describe_frames(frames):
    descriptions = []
    for frame in frames:
        frame_description = describe_frame(frame)
        if frame_description:
            descriptions.append(frame_description)
    return descriptions
  
def final_description(descriptions):
    prompt = "Use the following video frame's text description to write a description for the video. Do not mention frames/scenes or images, just describe what the video should be based on the frames.\nFrame descriptions:"
    for description in descriptions:
        prompt += f"\n- {description}"
        
    req = requests.post('https://ai.ince.pt/projects/mixtral/question', auth=basic, json={"question": prompt, "lite": True}, timeout=190)
    output = req.json()
    return output["answer"]

def fetch_frames(cap, interval=10):
    if not cap.isOpened():
        print("Error opening video file")
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_skip = int(fps * interval)
    frame_count = 0
    frames = []

    while cap.isOpened():
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_count)
        ret, frame = cap.read()

        if not ret:
            break

        frames.append(frame)
        frame_count += frame_skip

    cap.release()
    return frames

def describe_video_youtube(video_path, interval=10):
    frames = fetch_frames(cap_from_youtube(video_path, '480p'), interval)
    descriptions = describe_frames(frames)
    return final_description(descriptions)



def describe_video_file(video_path, interval=10):
    frames = fetch_frames(cv2.VideoCapture(video_path), interval)
    descriptions = describe_frames(frames)
    return final_description(descriptions)

#print(describe_video_file('sample.mp4', 10))
print(describe_video_youtube('https://youtu.be/LXb3EKWsInQ', 30))  
