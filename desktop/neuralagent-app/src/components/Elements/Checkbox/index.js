import React from 'react';
import {
  CheckboxContainer,
  CheckboxIcon,
  CheckboxTextContainer,
  CheckboxTitle,
  CheckboxHint
} from './CheckboxElements';
import { ImCheckboxUnchecked, ImCheckboxChecked } from 'react-icons/im';

function PieCheckbox({ value=false, onChange, title, hint, color='var(--primary-color)' }) {
  return (
    <>
      <CheckboxContainer onClick={() => onChange(!value)}>
        <CheckboxIcon color={color}>
          {value ? <ImCheckboxChecked /> : <ImCheckboxUnchecked />}
        </CheckboxIcon>
        <CheckboxTextContainer>
          <CheckboxTitle color={color}>
            {title}
          </CheckboxTitle>
          {
            hint !== null ? 
            <CheckboxHint>
              {hint}
            </CheckboxHint> : <></>
          }
        </CheckboxTextContainer>
      </CheckboxContainer>
    </>
  );
}

export default PieCheckbox;