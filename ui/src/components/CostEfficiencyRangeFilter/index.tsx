/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Stack, TextField } from '@mui/material';
import { GLOBAL_BACKGROUND_COLOR, GLOBAL_BORDER_COLOR } from '@/common/styles';

interface CostEfficiencyRangeFilterProps {
  min: number;
  max: number;
  onMinChange: (value: number) => void;
  onMaxChange: (value: number) => void;
}

const inputSx = {
  width: 100,
  '& .MuiOutlinedInput-root': {
    height: 36,
    backgroundColor: GLOBAL_BACKGROUND_COLOR,
    '& fieldset': { borderColor: GLOBAL_BORDER_COLOR },
    '&:hover fieldset': { borderColor: GLOBAL_BORDER_COLOR },
    '&.Mui-focused fieldset': { borderColor: GLOBAL_BORDER_COLOR }
  },
  '& .MuiInputLabel-root': { color: '#ffffff99', fontSize: 13 },
  '& .MuiOutlinedInput-input': { color: '#ffffff', fontSize: 13, padding: '8px 10px' }
};

export const CostEfficiencyRangeFilter = ({ min, max, onMinChange, onMaxChange }: CostEfficiencyRangeFilterProps) => {
  return (
    <Stack direction="row" alignItems="center" gap="8px">
      <TextField
        type="number"
        label="Min"
        size="small"
        value={min}
        onChange={(e) => {
          const parsed = parseFloat(e.target.value);
          if (!isNaN(parsed)) onMinChange(parsed);
        }}
        slotProps={{ htmlInput: { step: 0.01 } }}
        sx={inputSx}
      />
      <TextField
        type="number"
        label="Max"
        size="small"
        value={max}
        onChange={(e) => {
          const parsed = parseFloat(e.target.value);
          if (!isNaN(parsed)) onMaxChange(parsed);
        }}
        slotProps={{ htmlInput: { step: 0.01 } }}
        sx={inputSx}
      />
    </Stack>
  );
};
