import cv2
import mediapipe
import numpy as np
import traceback
import torch
from torch import nn
from torchvision.models import swin_v2_b, Swin_V2_B_Weights

"""
240829 Test needs to be done
"""

class Speak_detector:
    def __init__(self, snapshot_path):
        self.snapshot_path = snapshot_path
        self.model = swin_v2_b()
        self.preprocess = Swin_V2_B_Weights.IMAGENET1K_V1.transforms()
        self.model.head = nn.Linear(self.model.head.in_features, 2)

        checkpoint = torch.load(snapshot_path)
        self.model = nn.DataParallel(self.model).cuda()
        # print(checkpoint.keys())
        # exit()
        self.model.module.load_state_dict(checkpoint['model'])

    def __call__(self, frame):
        frame = self.preprocess(frame)
        frame = frame.unsqueeze(0).cuda()
        with torch.no_grad():
            self.model.eval()
            output = self.model(frame) # ['silent', 'utter'] * batch_size
            _, predicted = torch.max(output, 1)
            return predicted.item()


class SpeakerMatcher:
    def __init__(self, video_list, segments):
        self.video_list = video_list
        # self.video_list = map(lambda x:x.split('/')[-1], video_list)
        self.segments = segments

        self.face_mesh = mediapipe.solutions.face_mesh
        self.face_mesh = self.face_mesh.FaceMesh(static_image_mode=True, max_num_faces=1, refine_landmarks=True, min_detection_confidence=0.5)

        self.speak_detector = Speak_detector('/NasData/home/ych/2024_Multicam/checkpoints/run0621_0339/snapshot_swin_v2_b_2_0.9563032640482664.pth')

    def euclidean_distance(self, point1, point2):
        point1 = np.array(point1)
        point2 = np.array(point2)
        return np.sqrt(np.sum((point1 - point2)**2))

    def is_mouth_open(self, landmarks, threshold=0.05):
        upper_lip_top_index = 13 
        lower_lip_bottom_index = 14 
        mouth_left_corner_index = 61 
        mouth_right_corner_index = 291  
        left_eye_index = 130 # 130
        right_eye_index = 263 # 263
        
        upper_lip_top = landmarks[upper_lip_top_index]
        lower_lip_bottom = landmarks[lower_lip_bottom_index]
        mouth_left_corner = landmarks[mouth_left_corner_index]
        mouth_right_corner = landmarks[mouth_right_corner_index]

        mouth_height = self.euclidean_distance(upper_lip_top, lower_lip_bottom)
        
        mouth_width = self.euclidean_distance(mouth_left_corner, mouth_right_corner)
        
        ratio = mouth_height / mouth_width

        return ratio > threshold

    def lip_detection_in_frame(self, frame):
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        lip_indexes = [61, 146, 146, 91, 91, 181, 181, 84, 84, 17, 17, 314, 314, 405, 405, 321,
                    321, 375, 375, 291, 61, 185, 185, 40, 40, 39, 39, 37, 37, 0, 0, 267, 267,
                    269, 269, 270, 270, 409, 409, 291, 78, 95, 95, 88, 88, 178, 178, 87, 87, 14,
                    14, 317, 317, 402, 402, 318, 318, 324, 324, 308, 78, 191, 191, 80, 80, 81,
                    81, 82, 82, 13, 13, 312, 312, 311, 311, 310, 310, 415, 415, 308,]

        lip_contour = [61, 185, 40, 39, 37, 0, 267, 270] + [146, 91, 181, 84, 17, 314, 405, 321]

        upper_lip_top_index = 13
        lower_lip_bottom_index = 14
        mouth_left_corner_index = 61
        mouth_right_corner_index = 291

        lip_landmarks = []
        lip_coords = []
        state = None
        try:
            results = self.face_mesh.process(frame)

            if results.multi_face_landmarks:
                
                face_landmarks = results.multi_face_landmarks[0]
                landmarks = {i: [landmark.x, landmark.y, landmark.z] for i, landmark in enumerate(face_landmarks)}
                
                state = self.is_mouth_open(landmarks)
                lip_landmarks = [landmarks[i][:-1] for i in lip_contour]
                lip_landmarks = [[round(x*frame.shape[1]), round(y*frame.shape[0])] for x, y in lip_landmarks]
            
                x,y,w,h = cv2.boundingRect(np.array(lip_landmarks))
                lip_coords = [x, y, x+w, y+h]
                
                return lip_coords, state # coords: x1, y1, x2, y2, state: True or False
            else:
                return None, None
            
        except Exception as e:
            print(e)
            traceback.print_exc()
            return None, None
    
    def match_speaker(self):
        for seg in self.segments:
            cnt_per_video = []
            for video in self.video_list: # video_num = speaker_num
                cnts = 0 
                print(video)
                # exit()
                cap = cv2.VideoCapture(video)
                while cap.isOpened():
                    ret, frame = cap.read()
                    current_frame = cap.get(cv2.CAP_PROP_POS_FRAMES)
                    # print("current_frame: ", current_frame)
                    if current_frame < seg[0]:
                        continue
                    if current_frame > seg[1]:
                        break
                            

                    if not ret:
                        break

                    lip_coords, state = self.lip_detection_in_frame(frame)
                    print(lip_coords, state)

                    if state:
                        lip_roi = frame[lip_coords[1]:lip_coords[3], lip_coords[0]:lip_coords[2]]
                        prob = self.speak_detector(frame)
                        if prob[0] < prob[1]:
                            cnts += 1
                cnt_per_video.append(cnts)
                cap.release()
            
                print(f"[{seg[0]}-{seg[1]}] : {video} : {cnt_per_video.index(max(cnt_per_video))}")
            

'''
pseudocode

video_list = [video1, video2, ...] 
segments = [(start1, end1), (start2, end2), ...] # first speaking segment of each speaker

for seg in segments:
    for video in video_list:
        cap = cv2.VideoCapture(video)
        current_frame = cap.get(cv2.CAP_PROP_POS_FRAMES)
        
        if current_frame < seg[0] or current_frame > seg[1]:
            continue
            
        ret, frame = cap.read()
'''             


# def euclidean_distance(point1, point2):
#     point1 = np.array(point1)
#     point2 = np.array(point2)
#     return np.sqrt(np.sum((point1 - point2)**2))

# def is_mouth_open(landmarks, threshold=0.05):
#     upper_lip_top_index = 13 
#     lower_lip_bottom_index = 14 
#     mouth_left_corner_index = 61 
#     mouth_right_corner_index = 291  
#     left_eye_index = 130 # 130
#     right_eye_index = 263 # 263
    
#     upper_lip_top = landmarks[upper_lip_top_index]
#     lower_lip_bottom = landmarks[lower_lip_bottom_index]
#     mouth_left_corner = landmarks[mouth_left_corner_index]
#     mouth_right_corner = landmarks[mouth_right_corner_index]

#     mouth_height = euclidean_distance(upper_lip_top, lower_lip_bottom)
    
#     mouth_width = euclidean_distance(mouth_left_corner, mouth_right_corner)
    
#     ratio = mouth_height / mouth_width

#     return ratio > threshold

# mp_face_mesh = mediapipe.solutions.face_mesh
# face_mesh = mp_face_mesh.FaceMesh(static_image_mode=True, max_num_faces=1, refine_landmarks=True, min_detection_confidence=0.5)

# def lip_detection_in_frame(frame):

#         frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

#         lip_indexes = [61, 146, 146, 91, 91, 181, 181, 84, 84, 17, 17, 314, 314, 405, 405, 321,
#                     321, 375, 375, 291, 61, 185, 185, 40, 40, 39, 39, 37, 37, 0, 0, 267, 267,
#                     269, 269, 270, 270, 409, 409, 291, 78, 95, 95, 88, 88, 178, 178, 87, 87, 14,
#                     14, 317, 317, 402, 402, 318, 318, 324, 324, 308, 78, 191, 191, 80, 80, 81,
#                     81, 82, 82, 13, 13, 312, 312, 311, 311, 310, 310, 415, 415, 308,]

#         lip_contour = [61, 185, 40, 39, 37, 0, 267, 270] + [146, 91, 181, 84, 17, 314, 405, 321] # lip_high: 0, lip_low: 17
        
#         upper_lip_top_index = 13 
#         lower_lip_bottom_index = 14 
#         mouth_left_corner_index = 61 
#         mouth_right_corner_index = 291  
        
#         lip_landmarks = []
#         lip_coords = []
#         state = None
#         try:
#             results = face_mesh.process(frame)

#             if results.multi_face_landmarks:
                
#                 face_landmarks = results.multi_face_landmarks[0]
#                 # print(len(face_landmarks.landmark))
#                 landmarks = {i: [landmark.x, landmark.y, landmark.z] for i, landmark in enumerate(face_landmarks.landmark)}
                
#                 state = is_mouth_open(landmarks)
#                 lip_landmarks = [landmarks[i][:-1] for i in lip_contour]
#                 lip_landmarks = [[round(x*frame.shape[1]), round(y*frame.shape[0])] for x, y in lip_landmarks]
#                 # print(lip_landmarks)
            
#                 # lip_coords = list(cv2.boundingRect(np.array(lip_landmarks))) # x, y, w, h
#                 x,y,w,h = cv2.boundingRect(np.array(lip_landmarks))
#                 # lip_coords = [lip_coords[0], lip_coords[1], lip_coords[0]+lip_coords[2], lip_coords[1]+lip_coords[3]] # x1, y1, x2, y2
#                 lip_coords = [x, y, x+w, y+h]
#                 # print(lip_coords)
#                 return lip_coords, state # coords: x1, y1, x2, y2, state: True or False
#             else:
#                 return None, None # coords: None, state: None

#         except Exception as e:
#             print(e)
#             traceback.print_exc()
#             return None, None # coords: None, state: None
        
    
