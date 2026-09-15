import React from 'react';
import Dialog from './Dialog';
import { Text } from './Typography';
import { Button } from './Button';
import { useSelector } from 'react-redux';

function YesNoDialog({ isOpen, setOpen, title, text, isDarkMode=false, onYesClicked }) {

  const isRTL = useSelector(state => state.isRTL);

  const yesClicked = () => {
    setOpen(false);
    if (onYesClicked !== null) {
      onYesClicked();
    }
  };

  return (
    <>
      <Dialog
        isOpen={isOpen}
        setOpen={setOpen}
        maxWidth='500px'
        title={title}
        padding="10px 20px"
        isDarkMode={isDarkMode}
        child={
          <>
            <Text color={isDarkMode ? 'rgba(255, 255, 255, 0.8)' : 'rgba(0, 0, 0, 0.8)'}>
              {text}
            </Text>
            <div style={{marginTop: '10px', display: 'flex', marginLeft: isRTL ? '0' : 'auto', marginRight: isRTL ? 'auto' : '0'}}>
              <Button color="transparent" padding="10px 15px" onClick={() => setOpen(false)} dark={isDarkMode}>
                No
              </Button>
              <Button color="transparent" padding="10px 15px" onClick={yesClicked} dark={isDarkMode}>
                Yes
              </Button>
            </div>
          </>
        }
      />
    </>
  );
}

export default YesNoDialog;