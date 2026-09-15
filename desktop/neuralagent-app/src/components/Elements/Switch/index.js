import React from 'react';
import {
  SwitchContainer,
  SwitchIcon,
  SwitchTextContainer,
  SwitchTitle
} from './Elements';
import { BsToggleOn, BsToggleOff } from 'react-icons/bs';

function TWSwitch({ value=false, onChange, title, color='' }) {
  return (
    <>
      <SwitchContainer onClick={() => onChange(!value)}>
        <SwitchIcon color={color}>
          {value ? <BsToggleOn /> : <BsToggleOff />}
        </SwitchIcon>
        <SwitchTextContainer>
          <SwitchTitle color={color}>
            {title}
          </SwitchTitle>
        </SwitchTextContainer>
      </SwitchContainer>
    </>
  );
}

export default TWSwitch;