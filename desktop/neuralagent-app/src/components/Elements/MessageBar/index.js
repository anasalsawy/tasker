import React from 'react';
import { MessageBarContainer } from './MessageBarElements';

const MessageBar = ({ message, backgroundColor }) => {
  return (
    <MessageBarContainer backgroundColor={backgroundColor}>
      <p style={{textAlign: 'center'}}>
        {message}
      </p>
    </MessageBarContainer>
  )
}

export default MessageBar;
