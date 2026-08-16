from typing import List

class RecursiveCharacterTextSplitter:
    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 150):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = ["\n\n", "\n", ". ", " ", ""]

    def split_text(self, text: str) -> List[str]:
        """Split a single text document recursively using hierarchy of separators."""
        return self._split(text, self.separators)

    def _split(self, text: str, separators: List[str]) -> List[str]:
        """Recursive helper logic."""
        if len(text) <= self.chunk_size:
            return [text]

        # Find separator to use
        separator = separators[-1]
        for s in separators:
            if s in text:
                separator = s
                break

        # Split text by separator
        if separator != "":
            splits = text.split(separator)
        else:
            splits = list(text)

        # Merge splits into chunks of target size
        chunks = []
        current_chunk = []
        current_length = 0

        for split in splits:
            split_len = len(split)
            # Add separator length back unless empty or first item
            sep_len = len(separator) if current_chunk else 0
            
            if current_length + split_len + sep_len > self.chunk_size:
                if current_chunk:
                    # Save current chunk
                    chunks.append(separator.join(current_chunk))
                    
                    # Keep overlap splits
                    # Roll back splits until length fits overlap constraints
                    overlap_chunk = []
                    overlap_len = 0
                    for prev_split in reversed(current_chunk):
                        prev_split_len = len(prev_split)
                        prev_sep_len = len(separator) if overlap_chunk else 0
                        if overlap_len + prev_split_len + prev_sep_len <= self.chunk_overlap:
                            overlap_chunk.insert(0, prev_split)
                            overlap_len += prev_split_len + prev_sep_len
                        else:
                            break
                    current_chunk = overlap_chunk
                    current_length = overlap_len
                
                # If a single split is larger than chunk_size, split it with next separators
                if split_len > self.chunk_size:
                    sub_chunks = self._split(split, separators[separators.index(separator) + 1:])
                    chunks.extend(sub_chunks[:-1])
                    if sub_chunks:
                        current_chunk.append(sub_chunks[-1])
                        current_length = len(sub_chunks[-1])
                else:
                    current_chunk.append(split)
                    current_length = split_len
            else:
                current_chunk.append(split)
                current_length += split_len + sep_len

        if current_chunk:
            chunks.append(separator.join(current_chunk))

        return [c.strip() for c in chunks if c.strip()]
