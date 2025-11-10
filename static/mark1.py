import cv2
import numpy as np  # For efficient array operations
import glob
import os
import imutils

wm_path = 'watermark.png'  # Use .png for alpha support
wm = cv2.imread(wm_path, cv2.IMREAD_UNCHANGED)  # Loads as BGRA (4 channels)
print("wm.shape=",wm.shape)

# Find all screenshot files matching the pattern
files = glob.glob("in/Screenshot*.png")
i = 0
for file_path in files:
    # Load the image
    img = cv2.imread(file_path)
    if img is None:
        print(f"Could not load {file_path}")
        continue
    
    # # Get dimensions
    # height, width = img.shape[:2]
    
    # Crop 48 pixels from the top (adjust indices if you want from bottom/sides, e.g., img[:, 48:] for left)
    # This assumes you want to remove a top status bar or similar; total height becomes height - 48
    # if height <= 48:
    #     print(f"Image {file_path} is too short to crop 48 pixels.")
    #     continue
    
    print(f"Image {file_path}")
    # cropped_img = img[:-48, :]
    # cv2.imshow('cropped', imutils.resize(cropped_img, height=720))
    # k = cv2.waitKey(0) & 0xFF
    # if k == 27:
    #   exit()
    
    # Inside your loop, for each main image (img):
    if len(wm.shape) == 3 and wm.shape[2] == 4:  # Confirm alpha channel exists
        # Extract channels from watermark: B, G, R, A
        b, g, r, a = cv2.split(wm)
        
        # Normalize alpha to [0, 1]
        alpha = a.astype(np.float32) / 255.0
        
        # Perform alpha blending for each channel
        # Main image channels (assuming img is BGR, 3-channel)
        result_b = img[:,:,0].astype(np.float32) * (1.0 - alpha) + b.astype(np.float32) * alpha
        result_g = img[:,:,1].astype(np.float32) * (1.0 - alpha) + g.astype(np.float32) * alpha
        result_r = img[:,:,2].astype(np.float32) * (1.0 - alpha) + r.astype(np.float32) * alpha
        
        # Merge channels back into BGR and convert to uint8
        cropped_img = cv2.merge([result_b, result_g, result_r]).astype(np.uint8)

        cv2.imwrite(f"out/Screenshot-{i:03d}.png", cropped_img)
        i += 1
    else:
        # Fallback if no alpha: just use the main image (or handle error)
        print("Warning: Watermark lacks alpha channel. Skipping overlay.")
        cropped_img = img.copy()  # Or your original crop: img[:-48, :]

    # Continue with your script (e.g., save cropped_img)

    # Option 1: Overwrite original (since you have backups)
    # cv2.imwrite(file_path, cropped_img)
    
    # # Option 2: Save as new file with "_cropped" suffix (safer)
    # base_name = os.path.splitext(file_path)[0]
    # new_file_path = base_name + "_cropped.png"
    # cv2.imwrite(new_file_path, cropped_img)
    
    # print(f"Cropped {file_path} and saved to {new_file_path}")

print("Processing complete.")