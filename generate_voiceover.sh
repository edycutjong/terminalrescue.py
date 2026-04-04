#!/bin/bash
# A simple script to convert pasted text into high-quality audio files on macOS.

echo "🎙️  Paste your text for the voiceover below."
echo "   (When you are done pasting, press [Ctrl+D] to generate the audio file)"
echo "--------------------------------------------------------"

# Read multi-line input from the user copying and pasting
text=$(cat)

# Generate a unique filename using timestamp
filename="docs/voiceover_$(date +%s).aiff"

# Use the crisp 'Samantha' voice to output to the file
say -v Samantha "$text" -o "$filename"

echo "--------------------------------------------------------"
echo "✅ Done! Your audio file has been saved to: $filename"
echo "You can drag and drop this file straight into your video editor."
